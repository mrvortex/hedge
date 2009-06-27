# Hedge - the Hybrid'n'Easy DG Environment
# Copyright (C) 2007 Andreas Kloeckner
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.




import numpy
import numpy.linalg as la
from hedge.tools import Rotation




def main(write_output=True) :
    from hedge.element import TriangularElement, TetrahedralElement
    from hedge.timestep import RK4TimeStepper
    from hedge.visualization import SiloVisualizer, VtkVisualizer
    from math import sin, cos, pi, exp, sqrt
    from hedge.data import TimeConstantGivenFunction, \
            GivenFunction, ConstantGivenFunction

    from hedge.backends import guess_run_context
    rcon = guess_run_context()

    dim = 2

    def boundary_tagger(fvi, el, fn, all_v):
        if el.face_normals[fn][0] > 0:
            return ["dirichlet"]
        else:
            return ["neumann"]

    if dim == 2:
        if rcon.is_head_rank:
            from hedge.mesh import make_disk_mesh
            mesh = make_disk_mesh(r=0.5, boundary_tagger=boundary_tagger)
        el_class = TriangularElement
    elif dim == 3:
        if rcon.is_head_rank:
            from hedge.mesh import make_ball_mesh
            mesh = make_ball_mesh(max_volume=0.001)
        el_class = TetrahedralElement
    else:
        raise RuntimeError, "bad number of dimensions"

    if rcon.is_head_rank:
        print "%d elements" % len(mesh.elements)
        mesh_data = rcon.distribute_mesh(mesh)
    else:
        mesh_data = rcon.receive_mesh()

    discr = rcon.make_discretization(mesh_data, el_class(3))
    stepper = RK4TimeStepper()
    vis = VtkVisualizer(discr, rcon, "fld")

    dt = discr.dt_factor(1)**2 / 5
    nsteps = int(1/dt)

    if rcon.is_head_rank:
        print "dt", dt
        print "nsteps", nsteps

    def u0(x, el):
        if la.norm(x) < 0.2:
            return 1
        else:
            return 0

    def coeff(x, el):
        if x[0] < 0:
            return 0.25
        else:
            return 1

    def dirichlet_bc(t, x):
        return 0

    def neumann_bc(t, x):
        return 2

    from hedge.pde import StrongHeatOperator
    op = StrongHeatOperator(discr.dimensions, 
            #coeff=coeff,
            dirichlet_tag="dirichlet",
            dirichlet_bc=TimeConstantGivenFunction(ConstantGivenFunction(0)),
            neumann_tag="neumann", 
            neumann_bc=TimeConstantGivenFunction(ConstantGivenFunction(1))
            )
    u = discr.interpolate_volume_function(u0)

    # diagnostics setup -------------------------------------------------------
    from pytools.log import LogManager, \
            add_general_quantities, \
            add_simulation_quantities, \
            add_run_info

    if write_output:
        log_file_name = "heat.dat"
    else:
        log_file_name = None

    logmgr = LogManager(log_file_name, "w", rcon.communicator)
    add_run_info(logmgr)
    add_general_quantities(logmgr)
    add_simulation_quantities(logmgr, dt)
    discr.add_instrumentation(logmgr)

    stepper.add_instrumentation(logmgr)

    from hedge.log import Integral, LpNorm
    u_getter = lambda: u
    logmgr.add_quantity(LpNorm(u_getter, discr, 1, name="l1_u"))
    logmgr.add_quantity(LpNorm(u_getter, discr, name="l2_u"))

    logmgr.add_watches(["step.max", "t_sim.max", "l2_u", "t_step.max"])

    # timestep loop -----------------------------------------------------------
    rhs = op.bind(discr)
    for step in range(nsteps):
        logmgr.tick()
        t = step*dt

        if step % 10 == 0 and write_output:
            visf = vis.make_file("fld-%04d" % step)
            vis.add_data(visf, [("u", u), ], time=t, step=step)
            visf.close()

        u = stepper(u, t, dt, rhs)
        # Check whether the error goes over a certain level. If so => Abort
        assert discr.norm(u) < 10




if __name__ == "__main__":
    main()




# entry points for py.test ----------------------------------------------------
from pytools.test import mark_test
@mark_test(long=True)
def test_heat():
    main(write_output=False)
