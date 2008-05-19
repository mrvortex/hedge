"""Precompiled-code discretization execution engine."""

from __future__ import division

__copyright__ = "Copyright (C) 2007 Andreas Kloeckner"

__license__ = """
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see U{http://www.gnu.org/licenses/}.
"""




import numpy
import numpy.linalg as la
import pyublas
import hedge.discretization
import hedge.optemplate
import pymbolic.mapper
import hedge._internal as _internal




# precompiled flux building block debug monkeypatches -------------------------
@monkeypatch_method(_internal.ConstantFlux)
def __repr__(self):
    return str(self.value)
@monkeypatch_method(_internal.NormalFlux)
def __repr__(self):
    return "n[%d]" % self.axis
@monkeypatch_method(_internal.PenaltyFlux)
def __repr__(self):
    return "penalty(%s)" % self.power
@monkeypatch_method(_internal.SumFlux)
def __repr__(self):
    return "(%s+%s)" % (self.operand1, self.operand2)
@monkeypatch_method(_internal.ProductFlux)
def __repr__(self):
    return "(%s*%s)" % (self.operand1, self.operand2)
@monkeypatch_method(_internal.NegativeFlux)
def __repr__(self):
    return "-%s" % self.operand
@monkeypatch_method(_internal.ChainedFlux)
def __repr__(self):
    #return "ChainedFlux(%s)" % self.child
    return str(self.child)
@monkeypatch_method(_internal.IfPositiveFlux)
def __repr__(self):
    return "(If %s>0 then %s else %s)" % (self.criterion, self.then_part, self.else_part)





class _FluxCoefficientCompiler(pymbolic.mapper.RecursiveMapper):
    def handle_unsupported_expression(self, expr):
        if isinstance(expr, _internal.Flux):
            return expr
        else:
            pymbolic.mapper.RecursiveMapper.\
                    handle_unsupported_expression(self, expr)

    def map_constant(self, expr):
        return _internal.ConstantFlux(expr)

    def map_sum(self, expr):
        return reduce(lambda f1, f2: _internal.SumFlux(
                    _internal.ChainedFlux(f1), 
                    _internal.ChainedFlux(f2)),
                (self.rec(c) for c in expr.children))

    def map_product(self, expr):
        return reduce(
                lambda f1, f2: _internal.ProductFlux(
                    _internal.ChainedFlux(f1), 
                    _internal.ChainedFlux(f2)),
                (self.rec(c) for c in expr.children))

    def map_negation(self, expr):
        return _internal.NegativeFlux(_internal.ChainedFlux(self.rec(expr.child)))

    def map_power(self, expr):
        base = self.rec(expr.base)
        result = base

        chain_base = _internal.ChainedFlux(base)

        assert isinstance(expr.exponent, int)

        for i in range(1, expr.exponent):
            result = _internal.ProductFlux(_internal.ChainedFlux(result), chain_base)

        return result

    def map_normal(self, expr):
        return _internal.NormalFlux(expr.axis)

    def map_penalty_term(self, expr):
        return _internal.PenaltyFlux(expr.power)

    def map_if_positive(self, expr):
        return _internal.IfPositiveFlux(
                _internal.ChainedFlux(self.rec(expr.criterion)),
                _internal.ChainedFlux(self.rec(expr.then)),
                _internal.ChainedFlux(self.rec(expr.else_)),
                )




class _FluxOpCompileMapper(hedge.optemplate.FluxDecomposer):
    def __init__(self):
        self.coeff_comp = _FluxCoefficientCompiler()

    def compile_coefficient(self, coeff):
        return self.coeff_comp(coeff)




class ExecutionMapper(hedge.optemplate.Evaluator,
        hedge.optemplate.BoundOpMapperMixin, 
        hedge.optemplate.LocalOpReducerMixin):
    def __init__(self, context, discr):
        pymbolic.mapper.evaluator.EvaluationMapper.__init__(self, context)
        self.discr = discr
        self.diff_rst_cache = {}

        if self.discr.instrumented:
            from pytools.log import time_and_count_function
            self.map_diff_base = \
                    time_and_count_function(
                            self.map_diff_base,
                            self.discr.diff_op_timer,
                            self.discr.diff_op_counter)
            self.map_mass_base = \
                    time_and_count_function(
                            self.map_mass_base,
                            self.discr.mass_op_timer,
                            self.discr.mass_op_counter)
            self.inner_flux = \
                    time_and_count_function(
                            self.scalar_inner_flux,
                            self.discr.inner_flux_timer,
                            self.discr.inner_flux_counter)
            self.bdry_flux = \
                    time_and_count_function(
                            self.scalar_bdry_flux,
                            self.discr.bdry_flux_timer,
                            self.discr.bdry_flux_counter)

    # implementation stuff ----------------------------------------------------
    def diff_rst(self, op, rst_axis, field):
        result = self.discr.volume_zeros()

        from hedge.tools import make_vector_target
        target = make_vector_target(field, result)

        target.begin(len(self.discr), len(self.discr))

        from hedge._internal import perform_elwise_operator
        for eg in self.discr.element_groups:
            perform_elwise_operator(eg.ranges, eg.ranges, 
                    op.matrices(eg)[rst_axis], target)

        target.finalize()

        return result

    def diff_xyz(self, op, expr, field, result):
        try:
            rst_derivatives = self.diff_rst_cache[op.__class__, expr]
        except KeyError:
            rst_derivatives = self.diff_rst_cache[op.__class__, expr] = \
                    [self.diff_rst(op, i, field) 
                            for i in range(self.discr.dimensions)]

        from hedge.tools import make_vector_target
        from hedge._internal import perform_elwise_scale

        for rst_axis in range(self.discr.dimensions):
            target = make_vector_target(rst_derivatives[rst_axis], result)

            target.begin(len(self.discr), len(self.discr))
            for eg in self.discr.element_groups:
                perform_elwise_scale(eg.ranges,
                        op.coefficients(eg)[op.xyz_axis][rst_axis],
                        target)
            target.finalize()
        return result

    def scalar_inner_flux(self, int_coeff, ext_coeff, field, out=None):
        if out is None:
            out = self.discr.volume_zeros()

        from hedge.tools import make_vector_target
        self.discr.perform_inner_flux(
                int_coeff, ext_coeff, 
                make_vector_target(field, out))
        return out


    def scalar_bdry_flux(self, int_coeff, ext_coeff, field, bfield, tag, out=None):
        if out is None:
            out = self.discr.volume_zeros()

        bdry = self.discr.get_boundary(tag)
        if not bdry.nodes:
            return 0

        from hedge.tools import make_vector_target
        self.discr._perform_boundary_flux(
                int_coeff, make_vector_target(field, out),
                ext_coeff, make_vector_target(bfield, out), 
                bdry)

        return out




    # entry points ------------------------------------------------------------
    def map_diff_base(self, op, field_expr):
        field = self.rec(field_expr)

        from hedge.tools import log_shape
        lshape = log_shape(field)
        result = self.discr.volume_zeros(lshape)

        from pytools import indices_in_shape
        for i in indices_in_shape(lshape):
            self.diff_xyz(op, field_expr[i], field[i], result[i])

        return result

    def map_mass_base(self, op, field_expr):
        field = self.rec(field_expr)

        from hedge.tools import log_shape, make_vector_target
        lshape = log_shape(field)
        result = self.discr.volume_zeros(lshape)

        from pytools import indices_in_shape
        from hedge._internal import perform_elwise_scaled_operator
        for i in indices_in_shape(lshape):
            target = make_vector_target(field[i], result[i])

            target.begin(len(self.discr), len(self.discr))
            for eg in self.discr.element_groups:
                perform_elwise_scaled_operator(eg.ranges, eg.ranges,
                       op.coefficients(eg), op.matrix(eg), 
                       target)
            target.finalize()

        return result

    def map_flux_coefficient(self, op, field_expr):
        from hedge.optemplate import BoundaryPair

        if isinstance(field_expr, BoundaryPair):
            bp = field_expr
            return self.scalar_bdry_flux(
                    op.int_coeff, op.ext_coeff,
                    self.rec(bp.field), self.rec(bp.bfield), 
                    bp.tag)
        else:
            field = self.rec(field_expr)
            return self.scalar_inner_flux(
                    op.int_coeff, op.ext_coeff,
                    field)




class Discretization(hedge.discretization.Discretization):
    # inner flux computation --------------------------------------------------
    def perform_inner_flux(self, int_flux, ext_flux, target):
        """Perform fluxes in the interior of the domain on the 
        given operator target.  This performs the contribution::

          M_{i,j} := \sum_{interior faces f} \int_f
            (  
               int_flux(f) * \phi_j
               + 
               ext_flux(f) * \phi_{opp(j)}
             )
             \phi_i
        
        on the given target. opp(j) denotes the dof with its node
        opposite from node j on the face opposite f.

        Thus the matrix product M*u, where u is the full volume field
        results in::

          v_i := M_{i,j} u_j
            = \sum_{interior faces f} \int_f
            (  
               int_flux(f) * u^-
               + 
               ext_flux(f) * u^+
             )
             \phi_i

        For more on operator targets, see src/cpp/op_target.hpp.

        Both local_flux and neighbor_flux must be instances of
        hedge.flux.Flux, i.e. compiled fluxes. Typically, you will
        not call this routine, it will be called for you by flux
        operators obtained by get_flux_operator().
        """
        from hedge._internal import perform_flux_on_one_target, ChainedFlux, NullTarget

        if isinstance(target, NullTarget):
            return

        ch_int = ChainedFlux(int_flux)
        ch_ext = ChainedFlux(ext_flux)

        target.begin(len(self.nodes), len(self.nodes))
        for fg in self.face_groups:
            nf = True
            if nf:
                fmm = fg.ldis_int.multi_face_mass_matrix()
            else:
                fmm = fg.ldis_int.face_mass_matrix()
            perform_flux_on_one_target(
                    fg, fmm, ch_int, ch_ext, target, nf)
        target.finalize()

    # boundary flux computation -----------------------------------------------
    def _perform_boundary_flux(self, 
            int_flux, int_target, 
            ext_flux, ext_target, 
            bdry):
        from hedge._internal import perform_flux, ChainedFlux

        ch_int = ChainedFlux(int_flux)
        ch_ext = ChainedFlux(ext_flux)

        int_target.begin(len(self.nodes), len(self.nodes))
        ext_target.begin(len(self.nodes), len(bdry.nodes))
        if bdry.nodes:
            for fg in bdry.face_groups:
                perform_flux(fg, fg.ldis_int.face_mass_matrix(), 
                        ch_int, int_target, 
                        ch_ext, ext_target)
        int_target.finalize()
        ext_target.finalize()

    # op template execution ---------------------------------------------------
    def preprocess_optemplate(self, optemplate):
        from hedge.optemplate import OperatorBinder, InverseMassContractor
        from pymbolic.mapper.constant_folder import CommutativeConstantFoldingMapper
        from traceback import print_stack
        result = (
#                InverseMassContractor()(
                    CommutativeConstantFoldingMapper()(
                        _FluxOpCompileMapper()(
                            OperatorBinder()(
                                optemplate))))#)
        #print result
        return result

    def run_preprocessed_optemplate(self, pp_optemplate, vars):
        return ExecutionMapper(vars, self)(pp_optemplate)
