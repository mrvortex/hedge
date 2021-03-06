"""Operator template language: primitives."""

from __future__ import division

__copyright__ = "Copyright (C) 2008 Andreas Kloeckner"

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
import pymbolic.primitives
import hedge.mesh





# {{{ variables ---------------------------------------------------------------
from hedge.tools.symbolic import CFunction

Field = pymbolic.primitives.Variable

def make_field(var_or_string):
    if not isinstance(var_or_string, pymbolic.primitives.Expression):
        return Field(var_or_string)
    else:
        return var_or_string




class ScalarParameter(pymbolic.primitives.Variable):
    """A placeholder for a user-supplied scalar variable."""

    def stringifier(self):
        from hedge.optemplate import StringifyMapper
        return StringifyMapper

    mapper_method = intern("map_scalar_parameter")

# }}}

# {{{ technical helpers -------------------------------------------------------
class OperatorBinding(pymbolic.primitives.AlgebraicLeaf):
    def __init__(self, op, field):
        self.op = op
        self.field = field

    def stringifier(self):
        from hedge.optemplate import StringifyMapper
        return StringifyMapper

    mapper_method = intern("map_operator_binding")

    def __getinitargs__(self):
        return self.op, self.field

    def is_equal(self, other):
        from hedge.tools import field_equal
        return (other.__class__ == self.__class__
                and other.op == self.op
                and field_equal(other.field, self.field))

    def get_hash(self):
        from hedge.tools import hashable_field
        return hash((self.__class__, self.op, hashable_field(self.field)))




class PrioritizedSubexpression(pymbolic.primitives.CommonSubexpression):
    """When the optemplate-to-code transformation is performed,
    prioritized subexpressions  work like common subexpression in
    that they are assigned their own separate identifier/register
    location. In addition to this behavior, prioritized subexpressions
    are evaluated with a settable priority, allowing the user to
    expedite or delay the evaluation of the subexpression.
    """

    def __init__(self, child, priority=0):
        pymbolic.primitives.CommonSubexpression.__init__(self, child)
        self.priority = priority

    def __getinitargs__(self):
        return (self.child, self.priority)

    def get_extra_properties(self):
        return {"priority": self.priority}




class BoundaryPair(pymbolic.primitives.AlgebraicLeaf):
    """Represents a pairing of a volume and a boundary field, used for the
    application of boundary fluxes.
    """

    def __init__(self, field, bfield, tag=hedge.mesh.TAG_ALL):
        self.field = field
        self.bfield = bfield
        self.tag = tag

    mapper_method = intern("map_boundary_pair")

    def stringifier(self):
        from hedge.optemplate.mappers import StringifyMapper
        return StringifyMapper

    def __getinitargs__(self):
        return (self.field, self.bfield, self.tag)

    def get_hash(self):
        from hedge.tools import hashable_field

        return hash((self.__class__,
            hashable_field(self.field),
            hashable_field(self.bfield),
            self.tag))

    def is_equal(self, other):
        from hedge.tools import field_equal
        return (self.__class__ == other.__class__
                and field_equal(other.field,  self.field)
                and field_equal(other.bfield, self.bfield)
                and other.tag == self.tag)


# }}}

# {{{ geometry data -----------------------------------------------------------
class BoundaryNormalComponent(pymbolic.primitives.AlgebraicLeaf):
    def __init__(self, boundary_tag, axis, quadrature_tag=None):
        self.boundary_tag = boundary_tag
        self.axis = axis
        self.quadrature_tag = quadrature_tag

    def stringifier(self):
        from hedge.optemplate.mappers import StringifyMapper
        return StringifyMapper

    def get_hash(self):
        return hash((self.__class__,)+self.__getinitargs__())

    def is_equal(self, other):
        return (other.__class__ == self.__class__
                and other.boundary_tag == self.boundary_tag
                and other.axis == self.axis
                and other.quadrature_tag == self.quadrature_tag)

    mapper_method = intern("map_normal_component")

    def __getinitargs__(self):
        return (self.boundary_tag, self.axis, self.quadrature_tag)




def make_normal(tag, dimensions):
    return numpy.array([BoundaryNormalComponent(tag, i)
        for i in range(dimensions)], dtype=object)




class GeometricFactorBase(pymbolic.primitives.AlgebraicLeaf):
    def __init__(self, quadrature_tag):
        """
        :param quadrature_tag: quadrature tag for the grid on
        which this geometric factor is needed, or None for
        nodal representation.
        """
        self.quadrature_tag = quadrature_tag

    def get_hash(self):
        return hash((self.__class__, self.quadrature_tag))

    def is_equal(self, other): 
        return (other.__class__ == self.__class__
                and other.quadrature_tag == self.quadrature_tag)

    def __getinitargs__(self):
        return (self.quadrature_tag,)




class Jacobian(GeometricFactorBase):
    def stringifier(self):
        from hedge.optemplate.mappers import StringifyMapper
        return StringifyMapper

    mapper_method = intern("map_jacobian")





class ForwardMetricDerivative(GeometricFactorBase):
    """
    Pointwise metric derivatives representing

    .. math::
    
        \frac{d x_{\mathtt{xyz\_axis}} }{d r_{\mathtt{rst\_axis}} }
    """

    def __init__(self, quadrature_tag, xyz_axis, rst_axis):
        """
        :param quadrature_tag: quadrature tag for the grid on
        which this geometric factor is needed, or None for
        nodal representation.
        """

        GeometricFactorBase.__init__(self, quadrature_tag)
        self.xyz_axis = xyz_axis
        self.rst_axis = rst_axis

    def stringifier(self):
        from hedge.optemplate.mappers import StringifyMapper
        return StringifyMapper

    def get_hash(self):
        return hash((self.__class__, self.quadrature_tag, 
            self.xyz_axis, self.rst_axis))

    def is_equal(self, other):
        return (other.__class__ == self.__class__
                and other.quadrature_tag == self.quadrature_tag
                and other.xyz_axis == self.xyz_axis
                and other.rst_axis == self.rst_axis
                )

    mapper_method = intern("map_forward_metric_derivative")

    def __getinitargs__(self):
        return (self.quadrature_tag, self.xyz_axis, self.rst_axis)




class InverseMetricDerivative(GeometricFactorBase):
    """
    Pointwise metric derivatives representing

    .. math::
    
        \frac{d r_{\mathtt{rst\_axis}} }{d x_{\mathtt{xyz\_axis}} }
    """

    def __init__(self, quadrature_tag, rst_axis, xyz_axis):
        """
        :param quadrature_tag: quadrature tag for the grid on
        which this geometric factor is needed, or None for
        nodal representation.
        """

        GeometricFactorBase.__init__(self, quadrature_tag)
        self.rst_axis = rst_axis
        self.xyz_axis = xyz_axis

    def stringifier(self):
        from hedge.optemplate.mappers import StringifyMapper
        return StringifyMapper

    def get_hash(self):
        return hash((self.__class__, self.quadrature_tag, 
            self.xyz_axis, self.rst_axis))
    def is_equal(self, other):
        return (other.__class__ == self.__class__
                and other.quadrature_tag == self.quadrature_tag
                and other.rst_axis == self.rst_axis
                and other.xyz_axis == self.xyz_axis
                )

    mapper_method = intern("map_inverse_metric_derivative")

    def __getinitargs__(self):
        return (self.quadrature_tag, self.rst_axis, self.xyz_axis)

# }}}




# vim: foldmethod=marker
