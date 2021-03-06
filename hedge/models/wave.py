# -*- coding: utf8 -*-
"""Wave equation operators."""

from __future__ import division

__copyright__ = "Copyright (C) 2009 Andreas Kloeckner"

__license__ = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""




import numpy
import hedge.mesh
from hedge.models import HyperbolicOperator
from hedge.second_order import CentralSecondDerivative




# {{{ constant-velocity -------------------------------------------------------
class StrongWaveOperator(HyperbolicOperator):
    """This operator discretizes the wave equation
    :math:`\\partial_t^2 u = c^2 \\Delta u`.

    To be precise, we discretize the hyperbolic system

    .. math::

        \partial_t u - c \\nabla \\cdot v = 0

        \partial_t v - c \\nabla u = 0

    The sign of :math:`v` determines whether we discretize the forward or the
    backward wave equation.

    :math:`c` is assumed to be constant across all space.
    """

    def __init__(self, c, dimensions, source_f=None,
            flux_type="upwind",
            dirichlet_tag=hedge.mesh.TAG_ALL,
            dirichlet_bc_f=None,
            neumann_tag=hedge.mesh.TAG_NONE,
            radiation_tag=hedge.mesh.TAG_NONE):
        assert isinstance(dimensions, int)

        self.c = c
        self.dimensions = dimensions
        self.source_f = source_f

        if self.c > 0:
            self.sign = 1
        else:
            self.sign = -1

        self.dirichlet_tag = dirichlet_tag
        self.neumann_tag = neumann_tag
        self.radiation_tag = radiation_tag

        self.dirichlet_bc_f = dirichlet_bc_f

        self.flux_type = flux_type

    def flux(self):
        from hedge.flux import FluxVectorPlaceholder, make_normal

        dim = self.dimensions
        w = FluxVectorPlaceholder(1+dim)
        u = w[0]
        v = w[1:]
        normal = make_normal(dim)

        from hedge.tools import join_fields
        flux_weak = join_fields(
                numpy.dot(v.avg, normal),
                u.avg * normal)

        if self.flux_type == "central":
            pass
        elif self.flux_type == "upwind":
            # see doc/notes/hedge-notes.tm
            flux_weak -= self.sign*join_fields(
                    0.5*(u.int-u.ext),
                    0.5*(normal * numpy.dot(normal, v.int-v.ext)))
        else:
            raise ValueError("invalid flux type '%s'" % self.flux_type)

        flux_strong = join_fields(
                numpy.dot(v.int, normal),
                u.int * normal) - flux_weak

        return -self.c*flux_strong

    def op_template(self):
        from hedge.optemplate import \
                make_vector_field, \
                BoundaryPair, \
                get_flux_operator, \
                make_nabla, \
                InverseMassOperator, \
                BoundarizeOperator

        d = self.dimensions

        w = make_vector_field("w", d+1)
        u = w[0]
        v = w[1:]

        # boundary conditions -------------------------------------------------
        from hedge.tools import join_fields


        # dirichlet BCs -------------------------------------------------------
        from hedge.optemplate import make_normal, Field

        dir_normal = make_normal(self.dirichlet_tag, d)

        dir_u = BoundarizeOperator(self.dirichlet_tag) * u
        dir_v = BoundarizeOperator(self.dirichlet_tag) * v
        if self.dirichlet_bc_f:
            # FIXME
            from warnings import warn
            warn("Inhomogeneous Dirichlet conditions on the wave equation "
                    "are still having issues.")

            dir_g = Field("dir_bc_u")
            dir_bc = join_fields(2*dir_g - dir_u, dir_v)
        else:
            dir_bc = join_fields(-dir_u, dir_v)

        # neumann BCs ---------------------------------------------------------
        neu_u = BoundarizeOperator(self.neumann_tag) * u
        neu_v = BoundarizeOperator(self.neumann_tag) * v
        neu_bc = join_fields(neu_u, -neu_v)

        # radiation BCs -------------------------------------------------------
        from hedge.optemplate import make_normal
        rad_normal = make_normal(self.radiation_tag, d)

        rad_u = BoundarizeOperator(self.radiation_tag) * u
        rad_v = BoundarizeOperator(self.radiation_tag) * v

        rad_bc = join_fields(
                0.5*(rad_u - self.sign*numpy.dot(rad_normal, rad_v)),
                0.5*rad_normal*(numpy.dot(rad_normal, rad_v) - self.sign*rad_u)
                )

        # entire operator -----------------------------------------------------
        nabla = make_nabla(d)
        flux_op = get_flux_operator(self.flux())

        from hedge.tools import join_fields
        result = (
                - join_fields(
                    -self.c*numpy.dot(nabla, v),
                    -self.c*(nabla*u)
                    )
                +
                InverseMassOperator() * (
                    flux_op(w)
                    + flux_op(BoundaryPair(w, dir_bc, self.dirichlet_tag))
                    + flux_op(BoundaryPair(w, neu_bc, self.neumann_tag))
                    + flux_op(BoundaryPair(w, rad_bc, self.radiation_tag))
                    ))

        if self.source_f is not None:
            result[0] += Field("source_u")

        return result

    def bind(self, discr):
        from hedge.mesh import check_bc_coverage
        check_bc_coverage(discr.mesh, [
            self.dirichlet_tag,
            self.neumann_tag,
            self.radiation_tag])

        compiled_op_template = discr.compile(self.op_template())

        def rhs(t, w):
            kwargs = {"w": w}
            if self.dirichlet_bc_f:
                kwargs["dir_bc_u"] = self.dirichlet_bc_f.boundary_interpolant(
                        t, discr, self.dirichlet_tag)

            if self.source_f is not None:
                kwargs["source_u"] = self.source_f.volume_interpolant(t, discr)

            return compiled_op_template(**kwargs)

        return rhs

    def max_eigenvalue(self, t, fields=None, discr=None):
        return abs(self.c)

# }}}




# {{{ variable-velocity -------------------------------------------------------
class VariableVelocityStrongWaveOperator(HyperbolicOperator):
    """This operator discretizes the wave equation
    :math:`\\partial_t^2 u = c^2 \\Delta u`.

    To be precise, we discretize the hyperbolic system

    .. math::

        \partial_t u - c \\nabla \\cdot v = 0

        \partial_t v - c \\nabla u = 0
    """

    def __init__(self, c, dimensions, source=None,
            flux_type="upwind",
            dirichlet_tag=hedge.mesh.TAG_ALL,
            neumann_tag=hedge.mesh.TAG_NONE,
            radiation_tag=hedge.mesh.TAG_NONE,
            time_sign=1,
            diffusion_coeff=None,
            diffusion_scheme=CentralSecondDerivative()
            ):
        """`c` is assumed to be positive and conforms to the
        :class:`hedge.data.ITimeDependentGivenFunction` interface.

        `source` also conforms to the
        :class:`hedge.data.ITimeDependentGivenFunction` interface.
        """
        assert isinstance(dimensions, int)

        self.c = c
        self.time_sign = time_sign
        self.dimensions = dimensions
        self.source = source

        self.dirichlet_tag = dirichlet_tag
        self.neumann_tag = neumann_tag
        self.radiation_tag = radiation_tag

        self.flux_type = flux_type

        self.diffusion_coeff = diffusion_coeff
        self.diffusion_scheme = diffusion_scheme

    # {{{ flux ----------------------------------------------------------------
    def flux(self):
        from hedge.flux import FluxVectorPlaceholder, make_normal

        dim = self.dimensions
        w = FluxVectorPlaceholder(2+dim)
        c = w[0]
        u = w[1]
        v = w[2:]
        normal = make_normal(dim)

        from hedge.tools import join_fields
        flux = self.time_sign*1/2*join_fields(
                c.ext * numpy.dot(v.ext, normal)
                - c.int * numpy.dot(v.int, normal),
                normal*(c.ext*u.ext - c.int*u.int))

        if self.flux_type == "central":
            pass
        elif self.flux_type == "upwind":
            flux += join_fields(
                    c.ext*u.ext - c.int*u.int,
                    c.ext*normal*numpy.dot(normal, v.ext)
                    - c.int*normal*numpy.dot(normal, v.int)
                    )
        else:
            raise ValueError("invalid flux type '%s'" % self.flux_type)

        return flux

    # }}}

    def bind_characteristic_velocity(self, discr):
        from hedge.optemplate.operators import (
                ElementwiseMaxOperator)
        from hedge.optemplate import Field
        velocity = ElementwiseMaxOperator()(Field("c"))

        from hedge.optemplate import Field
        compiled = discr.compile(velocity)

        def do(t, w):
            return compiled(c=self.c.volume_interpolant(t, discr))

        return do

    def op_template(self, with_sensor=False):
        from hedge.optemplate import \
                Field, \
                make_vector_field, \
                BoundaryPair, \
                get_flux_operator, \
                make_nabla, \
                InverseMassOperator, \
                BoundarizeOperator

        d = self.dimensions

        w = make_vector_field("w", d+1)
        u = w[0]
        v = w[1:]

        from hedge.tools import join_fields
        c = Field("c")
        flux_w = join_fields(c, w)

        # {{{ boundary conditions
        from hedge.flux import make_normal
        normal = make_normal(d)

        from hedge.tools import join_fields

        # Dirichlet
        dir_c = BoundarizeOperator(self.dirichlet_tag) * c
        dir_u = BoundarizeOperator(self.dirichlet_tag) * u
        dir_v = BoundarizeOperator(self.dirichlet_tag) * v

        dir_bc = join_fields(dir_c, -dir_u, dir_v)

        # Neumann
        neu_c = BoundarizeOperator(self.neumann_tag) * c
        neu_u = BoundarizeOperator(self.neumann_tag) * u
        neu_v = BoundarizeOperator(self.neumann_tag) * v

        neu_bc = join_fields(neu_c, neu_u, -neu_v)

        # Radiation
        from hedge.optemplate import make_normal
        rad_normal = make_normal(self.radiation_tag, d)

        rad_c = BoundarizeOperator(self.radiation_tag) * c
        rad_u = BoundarizeOperator(self.radiation_tag) * u
        rad_v = BoundarizeOperator(self.radiation_tag) * v

        rad_bc = join_fields(
                rad_c,
                0.5*(rad_u - self.time_sign*numpy.dot(rad_normal, rad_v)),
                0.5*rad_normal*(numpy.dot(rad_normal, rad_v) - self.time_sign*rad_u)
                )

        # }}}

        # {{{ diffusion -------------------------------------------------------
        from pytools.obj_array import with_object_array_or_scalar

        def make_diffusion(arg):
            if with_sensor or (
                    self.diffusion_coeff is not None and self.diffusion_coeff != 0):
                if self.diffusion_coeff is None:
                    diffusion_coeff = 0
                else:
                    diffusion_coeff = self.diffusion_coeff

                if with_sensor:
                    diffusion_coeff += Field("sensor")

                from hedge.second_order import SecondDerivativeTarget

                # strong_form here allows the reuse the value of grad u.
                grad_tgt = SecondDerivativeTarget(
                        self.dimensions, strong_form=True,
                        operand=arg)

                self.diffusion_scheme.grad(grad_tgt, bc_getter=None,
                        dirichlet_tags=[], neumann_tags=[])

                div_tgt = SecondDerivativeTarget(
                        self.dimensions, strong_form=False,
                        operand=diffusion_coeff*grad_tgt.minv_all)

                self.diffusion_scheme.div(div_tgt,
                        bc_getter=None,
                        dirichlet_tags=[], neumann_tags=[])

                return div_tgt.minv_all
            else:
                return 0

        # }}}

        # entire operator -----------------------------------------------------
        nabla = make_nabla(d)
        flux_op = get_flux_operator(self.flux())

        return (
                - join_fields(
                    -self.time_sign*c*numpy.dot(nabla, v) - make_diffusion(u),
                    -self.time_sign*c*(nabla*u) - with_object_array_or_scalar(
                        make_diffusion, v)
                    )
                +
                InverseMassOperator() * (
                    flux_op(flux_w)
                    + flux_op(BoundaryPair(flux_w, dir_bc, self.dirichlet_tag))
                    + flux_op(BoundaryPair(flux_w, neu_bc, self.neumann_tag))
                    + flux_op(BoundaryPair(flux_w, rad_bc, self.radiation_tag))
                    ))


    def bind(self, discr, sensor=None):
        from hedge.mesh import check_bc_coverage
        check_bc_coverage(discr.mesh, [
            self.dirichlet_tag,
            self.neumann_tag,
            self.radiation_tag])

        compiled_op_template = discr.compile(self.op_template(
            with_sensor=sensor is not None))

        def rhs(t, w):
            kwargs = {}
            if sensor is not None:
                kwargs["sensor"] = sensor(t, w)

            rhs = compiled_op_template(w=w,
                    c=self.c.volume_interpolant(t, discr),
                    **kwargs)

            if self.source is not None:
                rhs[0] += self.source.volume_interpolant(t, discr)

            return rhs

        return rhs

    def max_eigenvalue(self, t, fields=None, discr=None):
        # Gives the max eigenvalue of a vector of eigenvalues.
        # As the velocities of each node is stored in the velocity-vector-field
        # a pointwise dot product of this vector has to be taken to get the
        # magnitude of the velocity at each node. From this vector the maximum
        # values limits the timestep.

        c = self.c.volume_interpolant(t, discr)
        return discr.nodewise_max(c)

# }}}




# vim: foldmethod=marker
