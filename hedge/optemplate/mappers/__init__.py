"""Operator template mappers."""

from __future__ import division

__copyright__ = "Copyright (C) 2008 Andreas Kloeckner"

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
import pymbolic.primitives
import pymbolic.mapper.stringifier
import pymbolic.mapper.evaluator
import pymbolic.mapper.dependency
import pymbolic.mapper.substitutor
import pymbolic.mapper.constant_folder
import pymbolic.mapper.flop_counter
from pymbolic.mapper import CSECachingMapperMixin




# {{{ mixins ------------------------------------------------------------------
class LocalOpReducerMixin(object):
    """Reduces calls to mapper methods for all local differentiation
    operators to a single mapper method, and likewise for mass
    operators.
    """
    def map_diff(self, expr, *args, **kwargs):
        return self.map_diff_base(expr, *args, **kwargs)

    def map_minv_st(self, expr, *args, **kwargs):
        return self.map_diff_base(expr, *args, **kwargs)

    def map_stiffness(self, expr, *args, **kwargs):
        return self.map_diff_base(expr, *args, **kwargs)

    def map_stiffness_t(self, expr, *args, **kwargs):
        return self.map_diff_base(expr, *args, **kwargs)

    def map_quad_stiffness_t(self, expr, *args, **kwargs):
        return self.map_diff_base(expr, *args, **kwargs)

    def map_mass_base(self, expr, *args, **kwargs):
        return self.map_elementwise_linear(expr, *args, **kwargs)

    def map_mass(self, expr, *args, **kwargs):
        return self.map_mass_base(expr, *args, **kwargs)

    def map_inverse_mass(self, expr, *args, **kwargs):
        return self.map_mass_base(expr, *args, **kwargs)

    def map_quad_mass(self, expr, *args, **kwargs):
        return self.map_mass_base(expr, *args, **kwargs)



class FluxOpReducerMixin(object):
    """Reduces calls to mapper methods for all flux
    operators to a smaller number of mapper methods.
    """
    def map_flux(self, expr, *args, **kwargs):
        return self.map_flux_base(expr, *args, **kwargs)

    def map_bdry_flux(self, expr, *args, **kwargs):
        return self.map_flux_base(expr, *args, **kwargs)

    def map_quad_flux(self, expr, *args, **kwargs):
        return self.map_flux_base(expr, *args, **kwargs)

    def map_quad_bdry_flux(self, expr, *args, **kwargs):
        return self.map_flux_base(expr, *args, **kwargs)



class OperatorReducerMixin(LocalOpReducerMixin, FluxOpReducerMixin):
    """Reduces calls to *any* operator mapping function to just one."""
    def map_diff_base(self, expr, *args, **kwargs):
        return self.map_operator(expr, *args, **kwargs)

    map_elementwise_linear = map_diff_base
    map_flux_base = map_diff_base
    map_elementwise_max = map_diff_base
    map_boundarize = map_diff_base
    map_flux_exchange = map_diff_base
    map_quad_grid_upsampler = map_diff_base
    map_quad_int_faces_grid_upsampler = map_diff_base
    map_quad_bdry_grid_upsampler = map_diff_base




class CombineMapperMixin(object):
    def map_operator_binding(self, expr):
        return self.combine([self.rec(expr.op), self.rec(expr.field)])

    def map_boundary_pair(self, expr):
        return self.combine([self.rec(expr.field), self.rec(expr.bfield)])




class IdentityMapperMixin(LocalOpReducerMixin, FluxOpReducerMixin):
    def map_operator_binding(self, expr, *args, **kwargs):
        assert not isinstance(self, BoundOpMapperMixin), \
                "IdentityMapper instances cannot be combined with " \
                "the BoundOpMapperMixin"

        return expr.__class__(
                self.rec(expr.op, *args, **kwargs),
                self.rec(expr.field, *args, **kwargs))

    def map_boundary_pair(self, expr, *args, **kwargs):
        assert not isinstance(self, BoundOpMapperMixin), \
                "IdentityMapper instances cannot be combined with " \
                "the BoundOpMapperMixin"

        return expr.__class__(
                self.rec(expr.field, *args, **kwargs),
                self.rec(expr.bfield, *args, **kwargs),
                expr.tag)

    def map_elementwise_linear(self, expr, *args, **kwargs):
        assert not isinstance(self, BoundOpMapperMixin), \
                "IdentityMapper instances cannot be combined with " \
                "the BoundOpMapperMixin"

        # it's a leaf--no changing children
        return expr

    def map_scalar_parameter(self, expr, *args, **kwargs):
        # it's a leaf--no changing children
        return expr

    map_mass_base = map_elementwise_linear
    map_diff_base = map_elementwise_linear
    map_flux_base = map_elementwise_linear
    map_elementwise_max = map_elementwise_linear
    map_boundarize = map_elementwise_linear
    map_flux_exchange = map_elementwise_linear
    map_quad_grid_upsampler = map_elementwise_linear
    map_quad_int_faces_grid_upsampler = map_elementwise_linear
    map_quad_bdry_grid_upsampler = map_elementwise_linear

    map_normal_component = map_elementwise_linear




class BoundOpMapperMixin(object):
    def map_operator_binding(self, expr, *args, **kwargs):
        return expr.op.get_mapper_method(self)(expr.op, expr.field, *args, **kwargs)



# }}}
# {{{ basic mappers -----------------------------------------------------------
class CombineMapper(CombineMapperMixin, pymbolic.mapper.CombineMapper):
    pass




class DependencyMapper(
        CombineMapperMixin,
        pymbolic.mapper.dependency.DependencyMapper,
        OperatorReducerMixin):
    def __init__(self,
            include_operator_bindings=True,
            composite_leaves=None,
            **kwargs):
        if composite_leaves == False:
            include_operator_bindings = False
        if composite_leaves == True:
            include_operator_bindings = True

        pymbolic.mapper.dependency.DependencyMapper.__init__(self,
                composite_leaves=composite_leaves, **kwargs)

        self.include_operator_bindings = include_operator_bindings

    def map_operator_binding(self, expr):
        if self.include_operator_bindings:
            return set([expr])
        else:
            return CombineMapperMixin.map_operator_binding(self, expr)

    def map_operator(self, expr):
        return set()

    def map_scalar_parameter(self, expr):
        return set([expr])

    def map_normal_component(self, expr):
        return set()



class FlopCounter(
        CombineMapperMixin,
        pymbolic.mapper.flop_counter.FlopCounter):
    def map_operator_binding(self, expr):
        return self.rec(expr.field)

    def map_scalar_parameter(self, expr):
        return 0




class IdentityMapper(
        IdentityMapperMixin,
        pymbolic.mapper.IdentityMapper):
    pass





class SubstitutionMapper(pymbolic.mapper.substitutor.SubstitutionMapper,
        IdentityMapperMixin):
    pass



# }}}
# {{{ pre-processing ----------------------------------------------------------
class OperatorBinder(CSECachingMapperMixin, IdentityMapper):
    map_common_subexpression_uncached = \
            IdentityMapper.map_common_subexpression

    def map_product(self, expr):
        if len(expr.children) == 0:
            return expr

        from pymbolic.primitives import flattened_product, Product
        from hedge.optemplate import Operator, OperatorBinding

        first = expr.children[0]
        if isinstance(first, Operator):
            prod = flattened_product(expr.children[1:])
            if isinstance(prod, Product) and len(prod.children) > 1:
                from warnings import warn
                warn("Binding '%s' to more than one "
                        "operand in a product is ambiguous - "
                        "use the parenthesized form instead."
                        % first)
            return OperatorBinding(first, self.rec(prod))
        else:
            return first * self.rec(flattened_product(expr.children[1:]))




class OperatorSpecializer(CSECachingMapperMixin, IdentityMapper):
    """Guided by a typedict, substitutes more specialized operators
    for generic ones.
    """
    def __init__(self, typedict):
        """
        :param typedict: generated by
        :class:`hedge.optemplate.mappers.type_inference.TypeInferrer`.
        """
        self.typedict = typedict

    map_common_subexpression_uncached = \
            IdentityMapper.map_common_subexpression

    def map_operator_binding(self, expr):
        from hedge.optemplate.primitives import BoundaryPair

        from hedge.optemplate.operators import (
                MassOperator, QuadratureMassOperator,
                StiffnessTOperator, QuadratureStiffnessTOperator,
                QuadratureGridUpsampler, QuadratureBoundaryGridUpsampler,
                FluxOperatorBase, FluxOperator, QuadratureFluxOperator,
                BoundaryFluxOperator, QuadratureBoundaryFluxOperator,
                BoundarizeOperator)

        from hedge.optemplate.mappers.type_inference import (
                type_info, QuadratureRepresentation)

        # {{{ figure out field type
        try:
            field_type = self.typedict[expr.field]
        except TypeError:
            # numpy arrays are not hashable
            # has_quad_operand remains unset

            assert isinstance(expr.field, numpy.ndarray)
        else:
            try:
                field_repr_tag = field_type.repr_tag
            except AttributeError:
                # boundary pairs are not assigned types
                assert isinstance(expr.field, BoundaryPair)
                has_quad_operand = False
            else:
                has_quad_operand = isinstance(field_repr_tag,
                            QuadratureRepresentation)
        # }}}

        # {{{ elementwise operators
        if isinstance(expr.op, MassOperator) and has_quad_operand:
            return QuadratureMassOperator(field_repr_tag.quadrature_tag) \
                    (self.rec(expr.field))

        elif isinstance(expr.op, StiffnessTOperator) and has_quad_operand:
            return QuadratureStiffnessTOperator(
                    expr.op.xyz_axis, field_repr_tag.quadrature_tag) \
                    (self.rec(expr.field))

        elif (isinstance(expr.op, QuadratureGridUpsampler)
                and isinstance(field_type, type_info.BoundaryVectorBase)):
            # potential shortcut:
            #if (isinstance(expr.field, OperatorBinding)
                    #and isinstance(expr.field.op, BoundarizeOperator)):
                #return QuadratureBoundarizeOperator(
                        #expr.field.op.tag, expr.op.quadrature_tag)(
                                #self.rec(expr.field.field))

            return QuadratureBoundaryGridUpsampler(
                    expr.op.quadrature_tag, field_type.boundary_tag)(expr.field)
        # }}}

        elif isinstance(expr.op, BoundarizeOperator) and has_quad_operand:
            raise TypeError("BoundarizeOperator cannot be applied to "
                    "quadrature-based operands--use QuadUpsample(Boundarize(...))")

        # {{{ flux operator specialization 
        elif isinstance(expr.op, FluxOperatorBase):
            from pytools.obj_array import with_object_array_or_scalar

            repr_tag_cell = [None]

            def process_flux_arg(flux_arg):
                arg_repr_tag = self.typedict[flux_arg].repr_tag
                if repr_tag_cell[0] is None:
                    repr_tag_cell[0] = arg_repr_tag
                else:
                    # An error for this condition is generated by
                    # the type inference pass.

                    assert arg_repr_tag == repr_tag_cell[0]

            is_boundary = isinstance(expr.field, BoundaryPair)
            if is_boundary:
                bpair = expr.field
                with_object_array_or_scalar(process_flux_arg, bpair.field)
                with_object_array_or_scalar(process_flux_arg, bpair.bfield)
            else:
                with_object_array_or_scalar(process_flux_arg, expr.field)

            is_quad = isinstance(repr_tag_cell[0], QuadratureRepresentation)
            if is_quad:
                assert not expr.op.is_lift
                quad_tag = repr_tag_cell[0].quadrature_tag

            new_fld = self.rec(expr.field)
            flux = expr.op.flux

            if is_boundary:
                if is_quad:
                    return QuadratureBoundaryFluxOperator(
                            flux, quad_tag, bpair.tag)(new_fld)
                else:
                    return BoundaryFluxOperator(flux, bpair.tag)(new_fld)
            else:
                if is_quad:
                    return QuadratureFluxOperator(flux, quad_tag)(new_fld)
                else:
                    return FluxOperator(flux, expr.op.is_lift)(new_fld)
        # }}}

        else:
            return IdentityMapper.map_operator_binding(self, expr)

    def map_normal_component(self, expr):
        from hedge.optemplate.mappers.type_inference import (
                NodalRepresentation)

        if not isinstance(
                self.typedict[expr].repr_tag,
                NodalRepresentation):
            raise NotImplementedError("quadrature-grid nodal components")

        # a leaf, doesn't change
        return expr




# }}}
# {{{ stringification ---------------------------------------------------------
class StringifyMapper(pymbolic.mapper.stringifier.StringifyMapper):
    def __init__(self, constant_mapper=str, flux_stringify_mapper=None):
        pymbolic.mapper.stringifier.StringifyMapper.__init__(
                self, constant_mapper=constant_mapper)

        if flux_stringify_mapper is None:
            from hedge.flux import FluxStringifyMapper
            flux_stringify_mapper = FluxStringifyMapper()

        self.flux_stringify_mapper = flux_stringify_mapper

    def map_boundary_pair(self, expr, enclosing_prec):
        from pymbolic.mapper.stringifier import PREC_NONE
        return "BPair(%s, %s, %s)" % (
                self.rec(expr.field, PREC_NONE),
                self.rec(expr.bfield, PREC_NONE),
                repr(expr.tag))

    def map_diff(self, expr, enclosing_prec):
        return "Diff%d" % expr.xyz_axis

    def map_minv_st(self, expr, enclosing_prec):
        return "MInvST%d" % expr.xyz_axis

    def map_stiffness(self, expr, enclosing_prec):
        return "Stiff%d" % expr.xyz_axis

    def map_stiffness_t(self, expr, enclosing_prec):
        return "StiffT%d" % expr.xyz_axis

    def map_quad_stiffness_t(self, expr, enclosing_prec):
        return "Q[%s]StiffT%d" % (
                expr.quadrature_tag, expr.xyz_axis)

    def map_elementwise_linear(self, expr, enclosing_prec):
        return "ElWLin:%s" % expr.__class__.__name__

    def map_mass(self, expr, enclosing_prec):
        return "M"

    def map_inverse_mass(self, expr, enclosing_prec):
        return "InvM"

    def map_quad_mass(self, expr, enclosing_prec):
        return "Q[%s]M" % expr.quadrature_tag

    def map_flux(self, expr, enclosing_prec):
        from pymbolic.mapper.stringifier import PREC_NONE
        return "%s(%s)" % (
                expr.get_flux_or_lift_text(),
                self.flux_stringify_mapper(expr.flux, PREC_NONE))

    def map_bdry_flux(self, expr, enclosing_prec):
        from pymbolic.mapper.stringifier import PREC_NONE
        return "B[%s]%s(%s)" % (
                expr.boundary_tag,
                expr.get_flux_or_lift_text(),
                self.flux_stringify_mapper(expr.flux, PREC_NONE))

    def map_quad_flux(self, expr, enclosing_prec):
        from pymbolic.mapper.stringifier import PREC_NONE
        return "Q[%s]%s(%s)" % (
                expr.quadrature_tag,
                expr.get_flux_or_lift_text(),
                self.flux_stringify_mapper(expr.flux, PREC_NONE))

    def map_quad_bdry_flux(self, expr, enclosing_prec):
        from pymbolic.mapper.stringifier import PREC_NONE
        return "Q[%s]B[%s]%s(%s)" % (
                expr.quadrature_tag,
                expr.boundary_tag,
                expr.get_flux_or_lift_text(),
                self.flux_stringify_mapper(expr.flux, PREC_NONE))

    def map_whole_domain_flux(self, expr, enclosing_prec):
        # used from hedge.backends.cuda.optemplate
        if expr.is_lift:
            opname = "WLift"
        else:
            opname = "WFlux"

        from pymbolic.mapper.stringifier import PREC_NONE
        return "%s(%s)" % (opname,
                self.rec(expr.rebuild_optemplate(), PREC_NONE))

    def map_elementwise_max(self, expr, enclosing_prec):
        return "ElWMax"

    def map_boundarize(self, expr, enclosing_prec):
        return "Boundarize<tag=%s>" % expr.tag

    def map_flux_exchange(self, expr, enclosing_prec):
        return "FExch<idx=%s,rank=%d>" % (expr.index, expr.rank)

    def map_normal_component(self, expr, enclosing_prec):
        return "Normal<tag=%s>[%d]" % (expr.tag, expr.axis)

    def map_operator_binding(self, expr, enclosing_prec):
        from pymbolic.mapper.stringifier import PREC_NONE
        return "<%s>(%s)" % (
                self.rec(expr.op, PREC_NONE),
                self.rec(expr.field, PREC_NONE))

    def map_scalar_parameter(self, expr, enclosing_prec):
        return "ScalarPar[%s]" % expr.name

    def map_quad_grid_upsampler(self, expr, enclosing_prec):
        return "ToQuad[%s]" % expr.quadrature_tag

    def map_quad_int_faces_grid_upsampler(self, expr, enclosing_prec):
        return "ToIntFQuad[%s]" % expr.quadrature_tag

    def map_quad_bdry_grid_upsampler(self, expr, enclosing_prec):
        return "ToBdryQuad[%s,%s]" % (expr.quadrature_tag, expr.boundary_tag)




class PrettyStringifyMapper(
        pymbolic.mapper.stringifier.CSESplittingStringifyMapperMixin,
        StringifyMapper):
    def __init__(self):
        pymbolic.mapper.stringifier.CSESplittingStringifyMapperMixin.__init__(self)
        StringifyMapper.__init__(self)

        self.flux_to_number = {}
        self.flux_string_list = []

        self.bc_to_number = {}
        self.bc_string_list = []

        from hedge.flux import PrettyFluxStringifyMapper
        self.flux_stringify_mapper = PrettyFluxStringifyMapper()

    def get_flux_number(self, flux):
        try:
            return self.flux_to_number[flux]
        except KeyError:
            from pymbolic.mapper.stringifier import PREC_NONE
            str_flux = self.flux_stringify_mapper(flux, PREC_NONE)

            flux_number = len(self.flux_to_number)
            self.flux_string_list.append(str_flux)
            self.flux_to_number[flux] = flux_number
            return flux_number

    def map_boundary_pair(self, expr, enclosing_prec):
        try:
            bc_number = self.bc_to_number[expr]
        except KeyError:
            from pymbolic.mapper.stringifier import PREC_NONE
            str_bc = StringifyMapper.map_boundary_pair(self, expr, PREC_NONE)

            bc_number = len(self.bc_to_number)
            self.bc_string_list.append(str_bc)
            self.bc_to_number[expr] = bc_number

        return "BC%d@%s" % (bc_number, expr.tag)

    def map_operator_binding(self, expr, enclosing_prec):
        from hedge.optemplate import BoundarizeOperator
        if isinstance(expr.op, BoundarizeOperator):
            from pymbolic.mapper.stringifier import PREC_CALL, PREC_SUM
            return self.parenthesize_if_needed(
                    "%s@%s" % (
                        self.rec(expr.field, PREC_CALL),
                        expr.op.tag),
                    enclosing_prec, PREC_SUM)
        else:
            return StringifyMapper.map_operator_binding(
                    self, expr, enclosing_prec)

    def get_bc_strings(self):
        return ["BC%d : %s" % (i, bc_str)
                for i, bc_str in enumerate(self.bc_string_list)]

    def get_flux_strings(self):
        return ["Flux%d : %s" % (i, flux_str)
                for i, flux_str in enumerate(self.flux_string_list)]

    def map_flux(self, expr, enclosing_prec):
        return "%s%d" % (
                expr.get_flux_or_lift_text(),
                self.get_flux_number(expr.flux))

    def map_bdry_flux(self, expr, enclosing_prec):
        return "B[%s]%s%d" % (
                expr.boundary_tag,
                expr.get_flux_or_lift_text(),
                self.get_flux_number(expr.flux))

    def map_quad_flux(self, expr, enclosing_prec):
        return "Q[%s]%s%d" % (
                expr.quadrature_tag,
                expr.get_flux_or_lift_text(),
                self.get_flux_number(expr.flux))

    def map_quad_bdry_flux(self, expr, enclosing_prec):
        return "Q[%s]B[%s]%s%d" % (
                expr.quadrature_tag,
                expr.boundary_tag,
                expr.get_flux_or_lift_text(),
                self.get_flux_number(expr.flux))




class NoCSEStringifyMapper(StringifyMapper):
    def map_common_subexpression(self, expr, enclosing_prec):
        return self.rec(expr.child, enclosing_prec)




# }}}
# {{{ quadrature support ------------------------------------------------------
class QuadratureUpsamplerRemover(CSECachingMapperMixin, IdentityMapper):
    def __init__(self, quad_min_degrees):
        self.quad_min_degrees = quad_min_degrees

    map_common_subexpression_uncached = \
            IdentityMapper.map_common_subexpression

    def map_operator_binding(self, expr):
        from hedge.optemplate.operators import (
                QuadratureGridUpsampler,
                QuadratureInteriorFacesGridUpsampler)

        if isinstance(expr.op, (QuadratureGridUpsampler,
            QuadratureInteriorFacesGridUpsampler)):
            try:
                min_degree = self.quad_min_degrees[expr.op.quadrature_tag]
            except KeyError:
                from warnings import warn
                warn("No minimum degree for quadrature tag '%s' specified--"
                        "falling back to nodal evaluation" % expr.op.quadrature_tag)
                return expr.field
            else:
                if min_degree is None:
                    return self.rec(expr.field)
                else:
                    return expr.op(self.rec(expr.field))
        else:
            return IdentityMapper.map_operator_binding(self, expr)




# }}}
# {{{ bc-to-flux rewriting ----------------------------------------------------
class BCToFluxRewriter(CSECachingMapperMixin, IdentityMapper):
    """Operates on :class:`FluxOperator` instances bound to :class:`BoundaryPair`. If the
    boundary pair's *bfield* is an expression of what's available in the
    *field*, we can avoid fetching the data for the explicit boundary
    condition and just substitute the *bfield* expression into the flux. This
    mapper does exactly that.
    """

    map_common_subexpression_uncached = \
            IdentityMapper.map_common_subexpression

    def map_operator_binding(self, expr):
        from hedge.optemplate.operators import BoundaryFluxOperatorBase
        from hedge.optemplate.primitives import BoundaryPair
        from hedge.flux import FluxSubstitutionMapper, FieldComponent

        if not (isinstance(expr.op, BoundaryFluxOperatorBase)
                and isinstance(expr.field, BoundaryPair)):
            return IdentityMapper.map_operator_binding(self, expr)

        bpair = expr.field
        vol_field = bpair.field
        bdry_field = bpair.bfield
        flux = expr.op.flux

        bdry_dependencies = DependencyMapper(
                    include_calls="descend_args",
                    include_operator_bindings=True)(bdry_field)

        vol_dependencies = DependencyMapper(
                include_operator_bindings=True)(vol_field)

        vol_bdry_intersection = bdry_dependencies & vol_dependencies
        if vol_bdry_intersection:
            raise RuntimeError("Variables are being used as both "
                    "boundary and volume quantities: %s"
                    % ", ".join(str(v) for v in vol_bdry_intersection))

        # Step 1: Find maximal flux-evaluable subexpression of boundary field
        # in given BoundaryPair.

        class MaxBoundaryFluxEvaluableExpressionFinder(
                IdentityMapper, OperatorReducerMixin):
            def __init__(self, vol_expr_list):
                self.vol_expr_list = vol_expr_list
                self.vol_expr_to_idx = dict((vol_expr, idx)
                        for idx, vol_expr in enumerate(vol_expr_list))

                self.bdry_expr_list = []
                self.bdry_expr_to_idx = {}

            def register_boundary_expr(self, expr):
                try:
                    return self.bdry_expr_to_idx[expr]
                except KeyError:
                    idx = len(self.bdry_expr_to_idx)
                    self.bdry_expr_to_idx[expr] = idx
                    self.bdry_expr_list.append(expr)
                    return idx

            def register_volume_expr(self, expr):
                try:
                    return self.vol_expr_to_idx[expr]
                except KeyError:
                    idx = len(self.vol_expr_to_idx)
                    self.vol_expr_to_idx[expr] = idx
                    self.vol_expr_list.append(expr)
                    return idx

            def map_normal(self, expr):
                raise RuntimeError("Your operator template contains a flux normal. "
                        "You may find this confusing, but you can't do that. "
                        "It turns out that you need to use "
                        "hedge.optemplate.make_normal() for normals in boundary "
                        "terms of operator templates.")

            def map_normal_component(self, expr):
                if expr.tag != bpair.tag:
                    raise RuntimeError("BoundaryNormalComponent and BoundaryPair "
                            "do not agree about boundary tag: %s vs %s"
                            % (expr.tag, bpair.tag))

                from hedge.flux import Normal
                return Normal(expr.axis)

            def map_variable(self, expr):
                return FieldComponent(
                        self.register_boundary_expr(expr),
                        is_interior=False)

            map_subscript = map_variable

            def map_operator_binding(self, expr):
                from hedge.optemplate import (BoundarizeOperator,
                        FluxExchangeOperator, QuadratureBoundaryGridUpsampler)

                if isinstance(expr.op, BoundarizeOperator):
                    if expr.op.tag != bpair.tag:
                        raise RuntimeError("BoundarizeOperator and BoundaryPair "
                                "do not agree about boundary tag: %s vs %s"
                                % (expr.op.tag, bpair.tag))

                    return FieldComponent(
                            self.register_volume_expr(expr.field),
                            is_interior=True)

                elif isinstance(expr.op, FluxExchangeOperator):
                    from hedge.mesh import TAG_RANK_BOUNDARY
                    op_tag = TAG_RANK_BOUNDARY(expr.op.rank)
                    if bpair.tag != op_tag:
                        raise RuntimeError("BoundarizeOperator and FluxExchangeOperator "
                                "do not agree about boundary tag: %s vs %s"
                                % (op_tag, bpair.tag))
                    return FieldComponent(
                            self.register_boundary_expr(expr),
                            is_interior=False)

                elif isinstance(expr.op, QuadratureBoundaryGridUpsampler):
                    if bpair.tag != expr.op.boundary_tag:
                        raise RuntimeError("BoundarizeOperator "
                                "and QuadratureBoundaryGridUpsampler "
                                "do not agree about boundary tag: %s vs %s"
                                % (expr.op.boundary_tag, bpair.tag))
                    return FieldComponent(
                            self.register_boundary_expr(expr),
                            is_interior=False)

                else:
                    raise RuntimeError("Found '%s' in a boundary term. "
                            "To the best of my knowledge, no hedge operator applies "
                            "directly to boundary data, so this is likely in error."
                            % expr.op)

        from hedge.tools import is_obj_array
        if not is_obj_array(vol_field):
            vol_field = [vol_field]

        mbfeef = MaxBoundaryFluxEvaluableExpressionFinder(list(vol_field))
        new_bdry_field = mbfeef(bdry_field)

        # Step II: Substitute the new_bdry_field into the flux.
        def sub_bdry_into_flux(expr):
            if isinstance(expr, FieldComponent) and not expr.is_interior:
                if expr.index == 0 and not is_obj_array(bdry_field):
                    return new_bdry_field
                else:
                    return new_bdry_field[expr.index]
            else:
                return None

        new_flux = FluxSubstitutionMapper(sub_bdry_into_flux)(flux)

        from hedge.tools import is_zero, make_obj_array
        if is_zero(new_flux):
            return 0
        else:
            return type(expr.op)(new_flux, *expr.op.__getinitargs__()[1:])(
                    BoundaryPair(
                        make_obj_array([self.rec(e) for e in mbfeef.vol_expr_list]),
                        make_obj_array([self.rec(e) for e in mbfeef.bdry_expr_list]),
                        bpair.tag))




# }}}
# {{{ simplification / optimization -------------------------------------------
class CommutativeConstantFoldingMapper(
        pymbolic.mapper.constant_folder.CommutativeConstantFoldingMapper,
        IdentityMapperMixin):

    def __init__(self):
        pymbolic.mapper.constant_folder.CommutativeConstantFoldingMapper.__init__(self)
        self.dep_mapper = DependencyMapper()

    def is_constant(self, expr):
        return not bool(self.dep_mapper(expr))

    def map_operator_binding(self, expr):
        from hedge.tools import is_zero
        if is_zero(expr.field):
            return 0

        from hedge.optemplate.operators import FluxOperatorBase
        from hedge.optemplate.primitives import BoundaryPair

        if not (isinstance(expr.op, FluxOperatorBase)
                and isinstance(expr.field, BoundaryPair)):
            return IdentityMapperMixin.map_operator_binding(self, expr)

        # {{{ remove zeros from boundary fluxes

        bpair = expr.field
        vol_field = bpair.field
        bdry_field = bpair.bfield
        from pytools.obj_array import is_obj_array
        if not is_obj_array(vol_field):
            vol_field = [vol_field]
        if not is_obj_array(bdry_field):
            bdry_field = [bdry_field]

        from hedge.flux import FieldComponent
        subst_map = {}

        # process volume field
        new_vol_field = []
        new_idx = 0
        for i, flux_arg in enumerate(vol_field):
            fc = FieldComponent(i, is_interior=True)
            flux_arg = self.rec(flux_arg)

            if is_zero(flux_arg):
                subst_map[fc] = 0
            else:
                new_vol_field.append(flux_arg)
                subst_map[fc] = FieldComponent(new_idx, is_interior=True)
                new_idx += 1


        # process boundary field
        new_bdry_field = []
        new_idx = 0
        for i, flux_arg in enumerate(bdry_field):
            fc = FieldComponent(i, is_interior=False)
            flux_arg = self.rec(flux_arg)

            if is_zero(flux_arg):
                subst_map[fc] = 0
            else:
                new_bdry_field.append(flux_arg)
                subst_map[fc] = FieldComponent(new_idx, is_interior=False)
                new_idx += 1

        # substitute results into flux
        def sub_flux(expr):
            return subst_map.get(expr, expr)

        from hedge.flux import FluxSubstitutionMapper
        new_flux = FluxSubstitutionMapper(sub_flux)(expr.op.flux)

        from hedge.tools import is_zero, make_obj_array
        if is_zero(new_flux):
            return 0
        else:
            return type(expr.op)(new_flux, *expr.op.__getinitargs__()[1:])(
                    BoundaryPair(
                        make_obj_array(new_vol_field),
                        make_obj_array(new_bdry_field),
                        bpair.tag))

        # }}}




class EmptyFluxKiller(CSECachingMapperMixin, IdentityMapper):
    def __init__(self, mesh):
        IdentityMapper.__init__(self)
        self.mesh = mesh

    map_common_subexpression_uncached = \
            IdentityMapper.map_common_subexpression

    def map_operator_binding(self, expr):
        from hedge.optemplate import BoundaryFluxOperatorBase

        if (isinstance(expr.op, BoundaryFluxOperatorBase) and
            len(self.mesh.tag_to_boundary.get(expr.op.boundary_tag, [])) == 0):
            return 0
        else:
            return IdentityMapper.map_operator_binding(self, expr)




class _InnerDerivativeJoiner(pymbolic.mapper.RecursiveMapper):
    def map_operator_binding(self, expr, derivatives):
        from hedge.optemplate import DifferentiationOperator

        if isinstance(expr.op, DifferentiationOperator):
            derivatives.setdefault(expr.op, []).append(expr.field)
            return 0
        else:
            return DerivativeJoiner()(expr)

    def map_common_subexpression(self, expr, derivatives):
        # no use preserving these if we're moving derivatives around
        return self.rec(expr.child, derivatives)

    def map_sum(self, expr, derivatives):
        from pymbolic.primitives import flattened_sum
        return flattened_sum(tuple(
            self.rec(child, derivatives) for child in expr.children))

    def map_product(self, expr, derivatives):
        from hedge.optemplate import ScalarParameter

        def is_scalar(expr):
            return isinstance(expr, (int, float, complex, ScalarParameter))

        from pytools import partition
        scalars, nonscalars = partition(is_scalar, expr.children)

        if len(nonscalars) != 1:
            return DerivativeJoiner()(expr)
        else:
            from pymbolic import flattened_product
            factor = flattened_product(scalars)
            nonscalar, = nonscalars

            sub_derivatives = {}
            nonscalar = self.rec(nonscalar, sub_derivatives)
            def do_map(expr):
                if is_scalar(expr):
                    return expr
                else:
                    return self.rec(expr, derivatives)

            for operator, operands in sub_derivatives.iteritems():
                for operand in operands:
                    derivatives.setdefault(operator, []).append(
                            factor*operand)

            return factor*nonscalar

    def map_constant(self, expr, *args):
        return DerivativeJoiner()(expr)

    def map_scalar_parameter(self, expr, *args):
        return DerivativeJoiner()(expr)

    def map_if_positive(self, expr, *args):
        return DerivativeJoiner()(expr)

    def map_power(self, expr, *args):
        return DerivativeJoiner()(expr)

    # these two are necessary because they're forwarding targets
    def map_algebraic_leaf(self, expr, *args):
        return DerivativeJoiner()(expr)

    def map_quotient(self, expr, *args):
        return DerivativeJoiner()(expr)




class DerivativeJoiner(CSECachingMapperMixin, IdentityMapper):
    """Joins derivatives:

    .. math::

        \frac{\partial A}{\partial x} + \frac{\partial B}{\partial x}
        \rightarrow
        \frac{\partial (A+B)}{\partial x}.
    """
    map_common_subexpression_uncached = \
            IdentityMapper.map_common_subexpression

    def map_sum(self, expr):
        idj = _InnerDerivativeJoiner()

        def invoke_idj(expr):
            sub_derivatives = {}
            result = idj(expr, sub_derivatives)
            if not sub_derivatives:
                return expr
            else:
                for operator, operands in sub_derivatives.iteritems():
                    derivatives.setdefault(operator, []).extend(operands)

                return result

        derivatives = {}
        new_children = [invoke_idj(child)
                for child in expr.children]

        for operator, operands in derivatives.iteritems():
            new_children.insert(0, operator(
                sum(self.rec(operand) for operand in operands)))

        from pymbolic.primitives import flattened_sum
        return flattened_sum(new_children)




class _InnerInverseMassContractor(pymbolic.mapper.RecursiveMapper):
    def __init__(self, outer_mass_contractor):
        self.outer_mass_contractor = outer_mass_contractor

    def map_constant(self, expr):
        from hedge.tools import is_zero
        from hedge.optemplate import InverseMassOperator, OperatorBinding

        if is_zero(expr):
            return 0
        else:
            return OperatorBinding(
                    InverseMassOperator(),
                    self.outer_mass_contractor(expr))

    def map_algebraic_leaf(self, expr):
        from hedge.optemplate import InverseMassOperator, OperatorBinding

        return OperatorBinding(
                InverseMassOperator(),
                self.outer_mass_contractor(expr))

    def map_operator_binding(self, binding):
        from hedge.optemplate import (
                MassOperator, StiffnessOperator, StiffnessTOperator,
                DifferentiationOperator,
                MInvSTOperator, InverseMassOperator,
                FluxOperator, BoundaryFluxOperator)

        if isinstance(binding.op, MassOperator):
            return binding.field
        elif isinstance(binding.op, StiffnessOperator):
            return DifferentiationOperator(binding.op.xyz_axis)(
                    self.outer_mass_contractor(binding.field))
        elif isinstance(binding.op, StiffnessTOperator):
            return MInvSTOperator(binding.op.xyz_axis)(
                    self.outer_mass_contractor(binding.field))
        elif isinstance(binding.op, FluxOperator):
            assert not binding.op.is_lift

            return FluxOperator(binding.op.flux, is_lift=True)(
                    self.outer_mass_contractor(binding.field))
        elif isinstance(binding.op, BoundaryFluxOperator):
            assert not binding.op.is_lift

            return BoundaryFluxOperator(binding.op.flux, 
                        binding.op.boundary_tag, is_lift=True)(
                    self.outer_mass_contractor(binding.field))
        else:
            return InverseMassOperator()(
                self.outer_mass_contractor(binding))

    def map_sum(self, expr):
        return expr.__class__(tuple(self.rec(child) for child in expr.children))

    def map_product(self, expr):
        from hedge.optemplate import (
                InverseMassOperator, OperatorBinding, ScalarParameter)

        def is_scalar(expr):
            return isinstance(expr, (int, float, complex, ScalarParameter))

        from pytools import len_iterable
        nonscalar_count = len_iterable(ch
                for ch in expr.children
                if not is_scalar(ch))

        if nonscalar_count > 1:
            # too complicated, don't touch it
            return OperatorBinding(
                    InverseMassOperator(),
                    self.outer_mass_contractor(expr))
        else:
            def do_map(expr):
                if is_scalar(expr):
                    return expr
                else:
                    return self.rec(expr)
            return expr.__class__(tuple(
                do_map(child) for child in expr.children))





class InverseMassContractor(CSECachingMapperMixin, IdentityMapper):
    # assumes all operators to be bound
    map_common_subexpression_uncached = \
            IdentityMapper.map_common_subexpression

    def map_boundary_pair(self, bp):
        from hedge.optemplate import BoundaryPair
        return BoundaryPair(self.rec(bp.field), self.rec(bp.bfield), bp.tag)

    def map_operator_binding(self, binding):
        # we only care about bindings of inverse mass operators
        from hedge.optemplate import InverseMassOperator

        if isinstance(binding.op, InverseMassOperator):
            return _InnerInverseMassContractor(self)(binding.field)
        else:
            return binding.__class__(binding.op,
                    self.rec(binding.field))




# }}}
# {{{ error checker -----------------------------------------------------------
class ErrorChecker(CSECachingMapperMixin, IdentityMapper):
    map_common_subexpression_uncached = \
            IdentityMapper.map_common_subexpression

    def __init__(self, mesh):
        self.mesh = mesh

    def map_operator_binding(self, expr):
        from hedge.optemplate import DiffOperatorBase

        if isinstance(expr.op, DiffOperatorBase):
            if (self.mesh is not None
                    and expr.op.xyz_axis >= self.mesh.dimensions):
                raise ValueError("optemplate tries to differentiate along a "
                        "non-existent axis (e.g. Z in 2D)")

        # FIXME: Also check fluxes
        return IdentityMapper.map_operator_binding(self, expr)

    def map_normal(self, expr):
        if self.mesh is not None and expr.axis >= self.mesh.dimensions:
            raise ValueError("optemplate tries to differentiate along a "
                    "non-existent axis (e.g. Z in 2D)")

        return expr




# }}}
# {{{ collectors for various optemplate components --------------------------------
class CollectorMixin(LocalOpReducerMixin, FluxOpReducerMixin):
    def combine(self, values):
        from pytools import flatten
        return set(flatten(values))

    def map_constant(self, bpair):
        return set()

    map_elementwise_linear = map_constant
    map_diff_base = map_constant
    map_flux_base = map_constant
    map_variable = map_constant
    map_elementwise_max = map_constant
    map_boundarize = map_constant
    map_flux_exchange = map_constant
    map_normal_component = map_constant
    map_scalar_parameter = map_constant
    map_quad_grid_upsampler = map_constant
    map_quad_int_faces_grid_upsampler = map_constant
    map_quad_bdry_grid_upsampler = map_constant




class FluxCollector(CSECachingMapperMixin, CollectorMixin, CombineMapper):
    map_common_subexpression_uncached = \
            CombineMapper.map_common_subexpression

    def map_operator_binding(self, expr):
        from hedge.optemplate import FluxOperatorBase

        if isinstance(expr.op, FluxOperatorBase):
            result = set([expr])
        else:
            result = set()

        return result | CombineMapper.map_operator_binding(self, expr)




class BoundaryTagCollector(CollectorMixin, CombineMapper):
    def map_boundary_pair(self, bpair):
        return set([bpair.tag])




class BoundOperatorCollector(CSECachingMapperMixin, CollectorMixin, CombineMapper):
    def __init__(self, op_class):
        self.op_class = op_class

    map_common_subexpression_uncached = \
            CombineMapper.map_common_subexpression

    def map_operator_binding(self, expr):
        if isinstance(expr.op, self.op_class):
            result = set([expr])
        else:
            result = set()

        return result | CombineMapper.map_operator_binding(self, expr)



# }}}
# {{{ evaluation --------------------------------------------------------------
class Evaluator(pymbolic.mapper.evaluator.EvaluationMapper):
    def map_boundary_pair(self, bp):
        from hedge.optemplate.primitives import BoundaryPair
        return BoundaryPair(self.rec(bp.field), self.rec(bp.bfield), bp.tag)
# }}}




# vim: foldmethod=marker
