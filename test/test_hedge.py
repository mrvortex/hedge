from __future__ import division
import unittest




class TestHedge(unittest.TestCase):
    def test_newton_interpolation(self):
        from hedge.interpolation import newton_interpolation_function
        
        x = [-1.5, -0.75, 0, 0.75, 1.5]
        y = [-14.1014, -0.931596, 0, 0.931596, 14.1014]
        nf = newton_interpolation_function(x, y)

        errors = [abs(yi-nf(xi)) for xi, yi in zip(x, y)]
        #print errors
        self.assert_(sum(errors) < 1e-14)
    # -------------------------------------------------------------------------
    def test_orthonormality_jacobi_1d(self):
        from hedge.polynomial import jacobi_function, jacobi_function_2
        from hedge.quadrature import LegendreGaussQuadrature

        max_n = 7
        int = LegendreGaussQuadrature(4*max_n) # overkill...

        class WeightFunction:
            def __init__(self, alpha, beta):
                self.alpha = alpha
                self.beta = beta

            def __call__(self, x):
                return (1-x)**self.alpha * (1+x)**self.beta

        for alpha, beta, ebound in [
                (0, 0, 3e-14), 
                (1, 0, 4e-14), 
                (3, 2, 3e-14), 
                (0, 2, 3e-13), 
                (5, 0, 3e-13), 
                (3, 4, 1e-14)
                ]:
            from scipy.special.orthogonal import jacobi
            jac_f = [jacobi_function(alpha, beta, n) for n in range(max_n)]
            wf = WeightFunction(alpha, beta)
            maxerr = 0
            for i, fi in enumerate(jac_f):
                for j, fj in enumerate(jac_f):
                    result = int(lambda x: wf(x)*fi(x)*fj(x))

                    if i == j:
                        true_result = 1
                    else:
                        true_result = 0
                    err = abs(result-true_result)
                    maxerr = max(maxerr, err)
                    if abs(result-true_result) > ebound:
                        print "bad", alpha, beta, i, j, abs(result-true_result)
                    self.assert_(abs(result-true_result) < ebound)
            #print alpha, beta, maxerr
    # -------------------------------------------------------------------------
    def test_transformed_quadrature(self):
        from math import exp, sqrt, pi

        def gaussian_density(x, mu, sigma):
            return 1/(sigma*sqrt(2*pi))*exp(-(x-mu)**2/(2*sigma**2))

        from hedge.quadrature import LegendreGaussQuadrature, TransformedQuadrature

        mu = 17
        sigma = 12
        tq = TransformedQuadrature(LegendreGaussQuadrature(20), mu-6*sigma, mu+6*sigma)
        
        result = tq(lambda x: gaussian_density(x, mu, sigma))
        self.assert_(abs(result - 1) < 1e-9)
    # -------------------------------------------------------------------------
    def test_warp(self):
        n = 17
        from hedge.element import WarpFactorCalculator
        wfc = WarpFactorCalculator(n)

        self.assert_(abs(wfc.int_f(-1)) < 1e-15)
        self.assert_(abs(wfc.int_f(1)) < 2e-15)

        from hedge.quadrature import LegendreGaussQuadrature

        lgq = LegendreGaussQuadrature(n)
        self.assert_(abs(lgq(wfc)) < 7e-15)
    # -------------------------------------------------------------------------
    def test_tri_nodes(self):
        from hedge.element import TriangularElement

        n = 17
        tri = TriangularElement(n)
        unodes = list(tri.unit_nodes())
        self.assert_(len(unodes) == tri.node_count())

        eps = 1e-10
        for ux in unodes:
            self.assert_(ux[0] >= -1-eps)
            self.assert_(ux[1] >= -1-eps)
            self.assert_(ux[0]+ux[1] <= 1+eps)

        for i, j in tri.node_indices():
            self.assert_(i >= 0)
            self.assert_(j >= 0)
            self.assert_(i+j <= n)
    # -------------------------------------------------------------------------
    def test_tri_basis_grad(self):
        from itertools import izip
        from hedge.element import TriangularElement
        from random import uniform
        import pylinear.array as num
        import pylinear.computation as comp

        tri = TriangularElement(8)
        for bf, gradbf in izip(tri.basis_functions(), tri.grad_basis_functions()):
            for i in range(10):
                r = uniform(-0.95, 0.95)
                s = uniform(-0.95, -r-0.05)

                h = 1e-4
                gradbf_v = num.array(gradbf((r,s)))
                approx_gradbf_v = num.array([
                    (bf((r+h,s)) - bf((r-h,s)))/(2*h),
                    (bf((r,s+h)) - bf((r,s-h)))/(2*h)
                    ])
                self.assert_(comp.norm_infinity(approx_gradbf_v-gradbf_v) < h)
    # -------------------------------------------------------------------------
    def test_tri_face_node_distribution(self):
        """Test whether the nodes on the faces of the triangle are distributed 
        according to the same proportions on each face.

        If this is not the case, then reusing the same face mass matrix
        for each face would be invalid.
        """

        from hedge.element import TriangularElement
        import pylinear.array as num
        import pylinear.computation as comp

        tri = TriangularElement(8)
        unodes = tri.unit_nodes()
        projected_face_points = []
        for face_i in tri.face_indices():
            start = unodes[face_i[0]]
            end = unodes[face_i[-1]]
            dir = end-start
            dir /= comp.norm_2_squared(dir)
            pfp = num.array([dir*(unodes[i]-start) for i in face_i])
            projected_face_points.append(pfp)

        first_points =  projected_face_points[0]
        for points in projected_face_points[1:]:
            self.assert_(comp.norm_infinity(points-first_points) < 1e-15)
    # -------------------------------------------------------------------------
    def test_tri_face_normals_and_jacobians(self):
        """Check computed face normals and face jacobians
        """
        from hedge.element import TriangularElement
        from hedge.tools import AffineMap
        import pylinear.array as num
        import pylinear.computation as comp
        from pylinear.randomized import make_random_vector

        tri = TriangularElement(4)

        for i in range(50):
            vertices = [make_random_vector(2, num.Float) for vi in range(3)]
            map = tri.get_map_unit_to_global(vertices)

            unodes = tri.unit_nodes()
            nodes = [map(v) for v in unodes]
            normals, jacobians = tri.face_normals_and_jacobians(map)

            from operator import add
            face_nodes = set(reduce(add, [[f[0], f[-1]] for f in tri.face_indices()]))
            for face_i, normal, jac in zip(tri.face_indices(), normals, jacobians):
                mapped_start = nodes[face_i[0]]
                mapped_end = nodes[face_i[-1]]
                mapped_dir = mapped_end-mapped_start

                opp_node = (face_nodes - set([face_i[0], face_i[-1]])).__iter__().next()
                mapped_opposite = nodes[opp_node]

                start = unodes[face_i[0]]
                end = unodes[face_i[-1]]
                true_jac = comp.norm_2(mapped_end-mapped_start)/2

                #print abs(true_jac-jac)/true_jac
                #print "aft, bef", comp.norm_2(mapped_end-mapped_start),comp.norm_2(end-start)

                self.assert_(abs(true_jac - jac)/true_jac < 1e-13)
                self.assert_(abs(comp.norm_2(normal) - 1) < 1e-13)
                self.assert_(abs(normal*mapped_dir) < 1e-13)
                self.assert_((mapped_opposite-mapped_start)*normal < 0)
    # -------------------------------------------------------------------------
    def test_tri_map(self):
        from hedge.element import TriangularElement
        import pylinear.array as num
        import pylinear.computation as comp
        from pylinear.randomized import \
                make_random_vector

        n = 8
        tri = TriangularElement(n)

        node_dict = dict((ituple, idx) for idx, ituple in enumerate(tri.node_indices()))
        corner_indices = [node_dict[0,0], node_dict[n,0], node_dict[0,n]]
        unodes = tri.unit_nodes()
        corners = [unodes[i] for i in corner_indices]

        for i in range(10):
            vertices = [make_random_vector(2, num.Float) for vi in range(3)]
            map = tri.get_map_unit_to_global(vertices)
            global_corners = [map(pt) for pt in corners]
            for gc, v in zip(global_corners, vertices):
                self.assert_(comp.norm_2(gc-v) < 1e-12)
    # -------------------------------------------------------------------------
    def test_tri_map_jacobian_and_mass_matrix(self):
        from hedge.element import TriangularElement
        import pylinear.array as num
        import pylinear.computation as comp
        from pylinear.randomized import make_random_vector
        from math import sqrt, exp, pi

        edata = TriangularElement(9)
        ones = num.ones((edata.node_count(),))
        unit_tri_area = 2
        self.assert_(abs(ones*(edata.mass_matrix()*ones)-unit_tri_area) < 1e-11)

        for i in range(10):
            vertices = [make_random_vector(2, num.Float) for vi in range(3)]
            map = edata.get_map_unit_to_global(vertices)
            mat = num.zeros((2,2))
            mat[:,0] = (vertices[1] - vertices[0])
            mat[:,1] = (vertices[2] - vertices[0])
            tri_area = abs(comp.determinant(mat)/2)
            tri_area_2 = abs(unit_tri_area*map.jacobian)
            self.assert_(abs(tri_area - tri_area_2)/tri_area < 1e-15)
    # -------------------------------------------------------------------------
    def no_test_tri_mass_mat_gauss(self):
        """Check the integral of a Gaussian on a disk using the mass matrix"""

        # This is a bad test, since it's never exact. The Gaussian has infinite support,
        # and this *does* matter numerically.

        from hedge.mesh import make_disk_mesh
        from hedge.element import TriangularElement
        from hedge.discretization import Discretization
        from math import sqrt, exp, pi

        sigma_squared = 1/219.3

        mesh = make_disk_mesh()
        discr = Discretization(make_disk_mesh(), TriangularElement(4))
        f = discr.interpolate_volume_function(lambda x: exp(-x*x/(2*sigma_squared)))
        ones = discr.interpolate_volume_function(lambda x: 1)

        #discr.visualize_vtk("gaussian.vtk", [("f", f)])
        num_integral_1 = ones * discr.apply_mass_matrix(f)
        num_integral_2 = f * discr.apply_mass_matrix(ones)
        dim = 2
        true_integral = (2*pi)**(dim/2)*sqrt(sigma_squared)**dim
        err_1 = abs(num_integral_1-true_integral)
        err_2 = abs(num_integral_2-true_integral)
        self.assert_(err_1 < 1e-11)
        self.assert_(err_2 < 1e-11)
    # -------------------------------------------------------------------------
    def test_tri_mass_mat_trig(self):
        """Check the integral of some trig functions on a square using the mass matrix"""

        from hedge.mesh import make_square_mesh
        from hedge.element import TriangularElement
        from hedge.discretization import Discretization
        import pylinear.computation as comp
        from math import sqrt, pi, cos, sin

        mesh = make_square_mesh(a=-pi, b=pi, max_area=(2*pi/10)**2/2)
        discr = Discretization(mesh, TriangularElement(8))
        f = discr.interpolate_volume_function(lambda x: cos(x[0])**2*sin(x[1])**2)
        ones = discr.interpolate_volume_function(lambda x: 1)

        #discr.visualize_vtk("trig.vtk", [("f", f)])
        num_integral_1 = ones * discr.apply_mass_matrix(f)
        num_integral_2 = f * discr.apply_mass_matrix(ones)
        true_integral = pi**2
        err_1 = abs(num_integral_1-true_integral)
        err_2 = abs(num_integral_2-true_integral)
        #print err_1, err_2
        self.assert_(err_1 < 1e-10)
        self.assert_(err_2 < 1e-10)
    # -------------------------------------------------------------------------
    def test_tri_diff_mat(self):
        """Check differentiation matrix along the coordinate axes on a disk.
        
        Uses sines as the function to differentiate.
        """
        import pylinear.computation as comp
        from hedge.mesh import make_disk_mesh
        from hedge.element import TriangularElement
        from hedge.discretization import Discretization
        from math import sin, cos, sqrt

        for coord in [0, 1]:
            mesh = make_disk_mesh()
            discr = Discretization(make_disk_mesh(), TriangularElement(4))
            f = discr.interpolate_volume_function(lambda x: sin(3*x[coord]))
            df = discr.interpolate_volume_function(lambda x: 3*cos(3*x[coord]))

            df_num = discr.differentiate(coord, f)
            error = df_num - df
            discr.visualize_vtk("diff-err.vtk",
                    [("f", f), ("df", df), ("df_num", df_num), ("error", error)])

            linf_error = comp.norm_infinity(df_num-df)
            #print linf_error
            self.assert_(linf_error < 3e-5)
    # -------------------------------------------------------------------------
    def test_2d_gauss_theorem(self):
        """Verify Gauss's theorem explicitly on a mesh."""

        from hedge.element import TriangularElement
        from hedge.tools import AffineMap
        from hedge.mesh import make_disk_mesh
        from hedge.discretization import Discretization
        import pylinear.array as num
        import pylinear.computation as comp
        from pylinear.randomized import make_random_vector
        from math import sin, cos, sqrt, exp, pi

        class OneSidedFlux:
            def __init__(self, coordinate):
                self.coordinate = coordinate
            def local_coeff(self, face):
                return face.normal[self.coordinate]
            def neighbor_coeff(self, face):
                return 0

        one_sided_x = OneSidedFlux(0)
        one_sided_y = OneSidedFlux(1)

        def f1(x):
            return sin(3*x[0])+cos(3*x[1])
        def f2(x):
            return sin(2*x[0])+cos(x[1])

        edata = TriangularElement(2)

        discr = Discretization(make_disk_mesh(), edata)
        ones = discr.interpolate_volume_function(lambda x: 1)
        face_zeros = discr.boundary_zeros()
        face_ones = discr.interpolate_boundary_function(lambda x: 1)

        f1_v = discr.interpolate_volume_function(f1)
        f2_v = discr.interpolate_volume_function(f2)

        f1_f = discr.interpolate_boundary_function(f1)
        f2_f = discr.interpolate_boundary_function(f2)

        dx_v = discr.differentiate(0, f1_v)
        dy_v = discr.differentiate(1, f2_v)

        int_div = \
                ones*discr.apply_mass_matrix(dx_v) + \
                ones*discr.apply_mass_matrix(dy_v)

        boundary_int = (
                discr.lift_boundary_flux(one_sided_x, f1_v, face_zeros) +
                discr.lift_boundary_flux(one_sided_y, f2_v, face_zeros)
                )*ones

        self.assert_(abs(boundary_int-int_div) < 1e-15)

    # -------------------------------------------------------------------------
    def test_tri_gauss_theorem(self):
        """Verify Gauss's theorem explicitly on a couple of elements 
        in random orientation."""

        from hedge.element import TriangularElement
        from hedge.tools import AffineMap
        import pylinear.array as num
        import pylinear.computation as comp
        from pylinear.randomized import make_random_vector
        from operator import add
        from math import sin, cos, sqrt, exp, pi

        edata = TriangularElement(9)
        ones = num.ones((edata.node_count(),))
        face_ones = num.ones((len(edata.face_indices()[0]),))

        def f1(x):
            return sin(3*x[0])+cos(3*x[1])
        def f2(x):
            return sin(2*x[0])+cos(x[1])

        def d(imap, coordinate, field):
            col = imap.matrix[:, coordinate]
            matrices = edata.differentiation_matrices()
            return reduce(add, (dmat*coeff*field
                        for dmat, coeff in zip(matrices, col)))

        array = num.array

        triangles = [
                [array([-7.1687642250744492, 0.63058995062684642]), array([9.9744219044921199, 6.6530989283689781]), array([12.269380138171147, -17.529689194536481])],
                [array([-3.1285787297852634, -16.579403405465403]), array([-5.2882160938912515, -6.2209234150214137]), array([11.251223490342774, 4.6571427341871727])],
                [array([4.7407472917152553, -18.406868078408063]), array([1.8224524488556271, 11.551374404003361]), array([2.523148394963088, 1.632574414790982])],
                [array([-11.523714017493292, -14.2820557378961]), array([-0.44311816855771136, 19.572194735728861]), array([5.2855990566779445, -9.8743423935894388])],
                [array([1.113949150102217, -3.2255502625302639]), array([-13.028732972681315, 2.1525752429773379]), array([-2.3929000970202705, 6.2884649052982198])],
                [array([-8.0878061368549741, -14.604092423350167]), array([4.5339922477199996, 8.3770287646932022]), array([-5.2180549365480156, -1.9930760171433717])],
                [array([-1.9047012017294165, -3.6517882549544485]), array([3.1461902282192784, 5.7397849191668229]), array([-11.072761256907262, -8.3758508470287509])],
                [array([8.6609581113102934, 9.1121629958018566]), array([3.8230948675835497, -14.004679313330751]), array([10.975623610855521, 1.6267418698764553])],
                [array([13.959685276941629, -12.201892555481464]), array([-7.8057604576925499, -3.5283871457281757]), array([-0.41961743047735317, -3.2615635891671872])],
                [array([-9.8469907360335078, 6.0635407355366242]), array([7.8727080309703439, 7.634505157189091]), array([-2.7723038834027118, 8.5441656500931789])],
                ]

        for vertices in triangles:
            map = edata.get_map_unit_to_global(vertices)
            imap = map.inverted()

            mapped_points = [map(node) for node in edata.unit_nodes()]
            f1_n = num.array([f1(x) for x in mapped_points])
            f2_n = num.array([f2(x) for x in mapped_points])

            dx_n = d(imap, 0, f1_n)
            dy_n = d(imap, 1, f2_n)

            int_div_f = abs(map.jacobian)*(
                    ones*edata.mass_matrix()*dx_n +
                    ones*edata.mass_matrix()*dy_n
                    )

            normals, jacobians = edata.face_normals_and_jacobians(map)
            boundary_sum = sum(
                    sum(
                        fjac * face_ones * edata.face_mass_matrix() 
                        * num.take(f_n, face_indices) * n_coord
                        for f_n, n_coord in zip([f1_n, f2_n], n))
                    for face_indices, n, fjac
                    in zip(edata.face_indices(), normals, jacobians)
                    )
            #print abs(boundary_sum-int_div_f)
            self.assert_(abs(boundary_sum-int_div_f) < 6e-13)
    # -------------------------------------------------------------------------
    def test_cubature(self):
        """Test the integrity of the cubature data."""

        from hedge.cubature import integrate_on_tetrahedron, TetrahedronCubatureData

        for i in range(len(TetrahedronCubatureData)):
            self.assert_(abs(integrate_on_tetrahedron(i+1, lambda x: 1)-2) < 1e-14)
    # -------------------------------------------------------------------------
    def test_tri_orthogonality(self):
        from hedge.cubature import integrate_on_tetrahedron, TetrahedronCubatureData
        from hedge.element import TriangularElement

        for order, ebound in [
                (1, 2e-15),
                (3, 4e-15),
                (4, 3e-15),
                #(7, 3e-14),
                #(9, 2e-13),
                ]:
            edata = TriangularElement(order)
            basis = edata.basis_functions()

            maxerr = 0
            for i, f in enumerate(basis):
                for j, g in enumerate(basis):
                    if i == j:
                        true_result = 1
                    else:
                        true_result = 0
                    result = integrate_on_tetrahedron(2*order, lambda x: f(x)*g(x))
                    err = abs(result-true_result)
                    maxerr = max(maxerr, err)
                    if err > ebound:
                        print "bad", order,i,j, err
                    self.assert_(err < ebound)
            #print order, maxerr
    # -------------------------------------------------------------------------
    def test_1d_mass_matrix_vs_quadrature(self):
        from hedge.quadrature import LegendreGaussQuadrature
        from hedge.polynomial import legendre_vandermonde
        import pylinear.array as num
        import pylinear.computation as comp
        import numpy

        for n in range(13):
            lgq = LegendreGaussQuadrature(n)
            vdm = legendre_vandermonde(lgq.points, n)
            mass_mat = 1/(vdm*vdm.T)
            ones = num.ones((mass_mat.shape[0],))
            self.assert_(comp.norm_infinity(
                    ((vdm*vdm.T) <<num.solve>> ones)
                    -
                    num.array(lgq.weights)) < 2e-14)
    # -------------------------------------------------------------------------
    def test_mapping_differences_tri(self):
        """Check that triangle interpolation is independent of mapping to reference
        """
        from hedge.element import TriangularElement
        import pylinear.array as num
        import pylinear.computation as comp
        from pylinear.randomized import make_random_vector
        from random import random
        from pytools import generate_permutations

        def shift(list):
            return list[1:] + [list[0]]

        class LinearCombinationOfFunctions:
            def __init__(self, coefficients, functions, premap):
                self.coefficients = coefficients
                self.functions = functions
                self.premap = premap

            def __call__(self, x):
                return sum(coeff*f(self.premap(x)) for coeff, f in 
                        zip(self.coefficients, self.functions))

        def random_barycentric_coordinates(dim):
            remain = 1
            coords = []
            for i in range(dim):
                coords.append(random() * remain)
                remain -= coords[-1]
            coords.append(remain)
            return coords

        tri = TriangularElement(5)

        for trial_number in range(10):
            vertices = [make_random_vector(2, num.Float) for vi in range(3)]
            map = tri.get_map_unit_to_global(vertices)
            nodes = [map(node) for node in tri.unit_nodes()]
            node_values = num.array([random() for node in nodes])

            functions = []
            for pvertices in generate_permutations(vertices):
                pmap = tri.get_map_unit_to_global(pvertices)
                pnodes = [pmap(node) for node in tri.unit_nodes()]

                # map from pnode# to node#
                nodematch = {}
                for pi, pn in enumerate(pnodes):
                    for i, n in enumerate(nodes):
                        if comp.norm_2(n - pn) < 1e-13:
                            nodematch[pi] = i
                            break

                pnode_values = num.array([node_values[nodematch[pi]] 
                        for pi in range(len(nodes))])

                interp_f = LinearCombinationOfFunctions(
                        tri.vandermonde() <<num.solve>> pnode_values,
                        tri.basis_functions(),
                        pmap.inverted())

                # verify interpolation property
                #for n, nv in zip(pnodes, pnode_values):
                    #self.assert_(abs(interp_f(n) - nv) < 1e-13)

                functions.append(interp_f)

            for subtrial_number in range(15):
                pt_in_element = sum(
                        coeff*vertex
                        for coeff, vertex in zip(
                            random_barycentric_coordinates(2),
                            vertices))
                f_values = [f(pt_in_element) for f in functions]
                avg = sum(f_values) / len(f_values)
                err = [abs(fv-avg) for fv in f_values]
                self.assert_(max(err) < 5e-13)
    # -------------------------------------------------------------------------
    def test_interior_fluxes_tri(self):
        """Compare surface integrals computed using interior fluxes
        with their known values.
        """

        from math import pi, sin, cos

        def round_trip_connect(start, end):
            for i in range(start, end):
                yield i, i+1
            yield end, start

        a = -pi
        b = pi
        points = [
                (a,0), (b,0), 
                (a,-1), (b,-1),
                (a,1), (b,1)
                ]
                
        import meshpy.triangle as triangle

        mesh_info = triangle.MeshInfo()
        mesh_info.set_points(points)
        mesh_info.set_faces(
                [(0,1),(1,3),(3,2),(2,0),(0,4),(4,5),(1,5)]
                )

        mesh_info.regions.resize(2)
        mesh_info.regions[0] = [
                0,-0.5, # coordinate
                1, # lower element tag
                0.1, # max area
                ]
        mesh_info.regions[1] = [
                0,0.5, # coordinate
                2, # upper element tag
                0.01, # max area
                ]

        generated_mesh = triangle.build(mesh_info, 
                attributes=True,
                area_constraints=True)
        #triangle.write_gnuplot_mesh("mesh.dat", generated_mesh)

        from hedge.mesh import ConformalMesh

        eltag_map = {1:"lower", 2:"upper"}
        mesh = ConformalMesh(
                generated_mesh.points,
                generated_mesh.elements,
                element_tags=dict((i, eltag_map[tag_i]) for i, tag_i in 
                    enumerate(generated_mesh.element_attributes)))

        from hedge.element import TriangularElement
        from hedge.discretization import Discretization
        discr = Discretization(mesh, TriangularElement(4))

        u_i = discr.interpolate_tag_volume_function(
                lambda x: sin(x[0]-x[1]),
                "lower")
        u_o = discr.interpolate_tag_volume_function(
                lambda x: cos(x[0]-x[1]),
                "upper")
        u = u_i + u_o

        #discr.visualize_vtk("dual.vtk", [("u", u)])

        from hedge.flux import local, neighbor, normal_2d
        res = discr.lift_interior_flux((local-neighbor)*normal_2d[1], u)
        #discr.visualize_vtk("dual.vtk", [("u", u), ("res", res)])
        ones = discr.interpolate_volume_function(lambda x: 1)
        self.assert_(abs(res*ones) < 5e-14)
    # -------------------------------------------------------------------------
    def test_symmetry_preservation_2d(self):
        """Test whether hedge preserves symmetry in 2D advection."""

        import pylinear.array as num

        def make_mesh():
            from hedge.mesh import ConformalMesh
            array = num.array

            points = [
                    array([-0.5, -0.5]), 
                    array([-0.5, 0.5]), 
                    array([0.5, 0.5]), 
                    array([0.5, -0.5]), 
                    array([0.0, 0.0]), 
                    array([-0.5, 0.0]), 
                    array([0.0, -0.5]), 
                    array([0.5, 0.0]), 
                    array([0.0, 0.5])]

            elements = [
                    [8,7,4],
                    [8,7,2],
                    [6,7,3],
                    [7,4,6],
                    [5,6,0],
                    [5,6,4],
                    [5,8,4],
                    [1,5,8],
                    ]

            boundary_tags = {
                    frozenset([3,7]): "inflow",
                    frozenset([2,7]): "inflow",
                    frozenset([6,3]): "outflow",
                    frozenset([2,8]): "outflow",
                    frozenset([1,8]): "outflow",
                    frozenset([1,5]): "outflow",
                    frozenset([0,5]): "outflow",
                    frozenset([0,6]): "outflow",
                    frozenset([3,6]): "outflow",
                    }
            return ConformalMesh(points, elements, boundary_tags)

        from hedge.discretization import Discretization, SymmetryMap
        from hedge.element import TriangularElement
        from hedge.flux import zero, normal_2d, jump_2d, local, neighbor, average
        from hedge.timestep import RK4TimeStepper
        from hedge.tools import dot
        from math import sqrt

        mesh = make_mesh()
        discr = Discretization(mesh, TriangularElement(4))

        a = num.array([1,0])

        def f(x):
            if x < 0.5: return 0
            else: return (x-0.5)

        def u_analytic(t, x):
            return f(a*x+t)

        u = discr.interpolate_volume_function(lambda x: u_analytic(0, x))
        dt = 1e-2
        nsteps = int(1/dt)

        def rhs_strong(t, u):
            bc = discr.interpolate_boundary_function(
                    lambda x: u_analytic(t, x),
                    "inflow")

            rhsint =   a[0]*discr.differentiate(0, u)
                    #+ a[1]*discr.differentiate(1, u)
            rhsflux = discr.lift_interior_flux(flux, u)
            rhsbdry = discr.lift_boundary_flux(flux, u, bc, "inflow")

            return rhsint-discr.apply_inverse_mass_matrix(rhsflux+rhsbdry)

        sym_map = SymmetryMap(discr, 
                lambda x: num.array([x[0], -x[1]]),
                {0:3, 2:1, 5:6, 7:4})

        for flux_name, flux in [
                ("lax-friedrichs",
                    dot(normal_2d, a) * (local-average)
                    + 0.5 *(local-neighbor)),
                ("central",
                    dot(normal_2d, a) * (local-average) * average),
                ]:
            stepper = RK4TimeStepper()
            for step in range(nsteps):
                u = stepper(u, step*dt, dt, rhs_strong)
                sym_error_u = u-sym_map(u)
                sym_error_u_l2 = sqrt(sym_error_u*discr.apply_mass_matrix(sym_error_u))
                self.assert_(sym_error_u_l2 < 1e-14)
    # -------------------------------------------------------------------------
    def test_convergence_advec_2d(self):
        """Test whether 2D advection actually converges."""

        import pylinear.array as num
        from hedge.mesh import make_disk_mesh
        from hedge.discretization import Discretization
        from hedge.element import TriangularElement
        from hedge.timestep import RK4TimeStepper
        from hedge.tools import EOCRecorder, dot
        from hedge.flux import zero, normal_2d, local, neighbor, average
        from math import sin, pi, sqrt

        a = num.array([1,0])

        def u_analytic(t, x):
            return sin(a*x+t)

        def boundary_tagger_circle(vertices, (v1, v2)):
            center = (num.array(vertices[v1])+num.array(vertices[v2]))/2
            
            if center * a > 0:
                return "inflow"
            else:
                return "outflow"

        mesh = make_disk_mesh(r=pi, boundary_tagger=boundary_tagger_circle, max_area=0.5)

        for flux_name, flux in [
                ("lax-friedrichs",
                    dot(normal_2d, a) * (local-average)
                    + 0.5 *(local-neighbor)),
                ("central",
                    dot(normal_2d, a) * (local-average) * average),
                ]:

            eoc_rec = EOCRecorder()

            for order in [1,2,3,4,5,6]:
                discr = Discretization(mesh, TriangularElement(order))

                u = discr.interpolate_volume_function(lambda x: u_analytic(0, x))
                dt = 1e-2
                nsteps = int(0.1/dt)

                def rhs_strong(t, u):
                    bc = discr.interpolate_boundary_function(
                            lambda x: u_analytic(t, x),
                            "inflow")

                    rhsint =   a[0]*discr.differentiate(0, u)
                            #+ a[1]*discr.differentiate(1, u)
                    rhsflux = discr.lift_interior_flux(flux, u)
                    rhsbdry = discr.lift_boundary_flux(flux, u, bc, "inflow")

                    return rhsint-discr.apply_inverse_mass_matrix(rhsflux+rhsbdry)

                stepper = RK4TimeStepper()
                for step in range(nsteps):
                    u = stepper(u, step*dt, dt, rhs_strong)

                u_true = discr.interpolate_volume_function(
                        lambda x: u_analytic(nsteps*dt, x))
                error = u-u_true
                error_l2 = sqrt(error*discr.apply_mass_matrix(error))
                eoc_rec.add_data_point(order, error_l2)
            self.assert_(eoc_rec.estimate_order_of_convergence()[0,1] > 7)
            #print "%s\n%s\n" % (flux_name.upper(), "-" * len(flux_name))
            #print eoc_rec.pretty_print(abscissa_label="Poly. Order", 
                    #error_label="L2 Error")
                




if __name__ == '__main__':
    unittest.main()