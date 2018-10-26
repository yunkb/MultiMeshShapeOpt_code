from dolfin import (ALE, cpp,
                    dof_to_vertex_map, Vertex, vertex_to_dof_map,
                    Constant, DirichletBC, Expression, SpatialCoordinate,
                    FacetNormal, FunctionSpace, Circumradius, VectorFunctionSpace,
                    Mesh, MeshValueCollection, MeshFunction,
                    assemble_multimesh,
                    MultiMesh, MultiMeshFunction, MultiMeshFunctionSpace,
                    MultiMeshDirichletBC, MultiMeshSubSpace,
                    XDMFFile, File, plot,
                    Point, VectorElement, FiniteElement,
                    interpolate, Function, Measure,
                    TestFunction, TrialFunction, assemble,
                    TestFunctions, TrialFunctions,
                    dX, dI, dI, dx, dC, dO,
                    inner, outer, grad, div, avg, jump, sym, tr, Identity,
                    solve, set_log_level, LogLevel)
from IPython import embed
from pdb import set_trace
from numpy import nan
from matplotlib.pyplot import show
set_log_level(LogLevel.ERROR)
class StokesSolver():
    def __init__(self, meshes, facetfunctions, cover_points,
                 bc_dict, move_dict, length_width):
        """
        Solve the stokes problem with multiple meshes.
        Arguments:
           meshes: List of dolfin meshes, in the order they should be added 
                   to the multimesh
           facetfunctions: List of FacetFunctions corresponding to the
                   meshes above
           cover_points: 
                   dict where the key is the mesh that should get covered cells,
                   value is at which point auto_cover should start
           bc_dict: Dictionary describing boundary conditions for the Stokes
                    problem
           move_dict: Dictionary describing which node that will be fixed and 
                   which are design variables in the optimization problem
           length_width: List containing the length and width of channel
                   without an obstacle. Needed to compute barycenter of 
                   obstacle
        """
        self.__init_multimesh(meshes, cover_points)
        self.mfs = facetfunctions
        self.move_dict = move_dict
        self.V2 = VectorElement("CG", meshes[0].ufl_cell(), 2)
        self.S1 = FiniteElement("CG", meshes[0].ufl_cell(), 1)
        self.VQ = MultiMeshFunctionSpace(self.multimesh, self.V2*self.S1)
        V = MultiMeshFunctionSpace(self.multimesh, self.V2)
        Q = MultiMeshFunctionSpace(self.multimesh, self.S1)
        self.__init_bcs(bc_dict)
        self.w = MultiMeshFunction(self.VQ, name="State")
        self.u = MultiMeshFunction(V, name="u")
        self.p = MultiMeshFunction(Q, name="p")

        self.f = Constant([0.]*self.multimesh.part(0).geometric_dimension())
        self.N = len(meshes)
        self.outu = [File("output/u_%d.pvd" %i) for i in range(self.N)]
        self.outp = [File("output/p_%d.pvd" %i) for i in range(self.N)]

        self.J = 0
        self.dJ = 0
        self.opt_it = 0
        self.vfac = 1e4
        self.bfac = 1e2
        self.length_width = length_width
        self.__init_geometric_quantities()        
        
    def __init_multimesh(self, meshes, cover_points):
        multimesh = MultiMesh()
        self.backup = []
        self.S = []
        for mesh in meshes:
            multimesh.add(mesh)
            self.backup.append(mesh.coordinates().copy())
            self.S.append(VectorFunctionSpace(mesh, "CG", 1))
        multimesh.build()
        for key in cover_points.keys():
            multimesh.auto_cover(key, cover_points[key])            
        self.multimesh = multimesh
        self.cover_points = cover_points

    def __init_bcs(self, bc_dict):
        """ 
        Initialize velocity dirichlet bcs on each mesh according to dictionary
        """
        V = MultiMeshSubSpace(self.VQ, 0)
        self.bcs = []
        for i in bc_dict:
            for marker in bc_dict[i]:
                bc = MultiMeshDirichletBC(V, bc_dict[i][marker],
                                          self.mfs[i], marker, i)
                self.bcs.append(bc)

    def __init_geometric_quantities(self):
        """
        Helper initializer to compute original volume and barycenter
        of the obstacle.
        """
        x = SpatialCoordinate(self.multimesh)
        V = MultiMeshFunctionSpace(self.multimesh, "CG", 1)
        x = interpolate(Expression("x[0]", degree=1), V)
        y = interpolate(Expression("x[1]", degree=1), V)
        fluid_vol = assemble_multimesh(Constant(1)*dx(domain=self.multimesh) +
                                       Constant(1)*dC(domain=self.multimesh))
        self.Vol0 = Constant(self.length_width[0]*self.length_width[1]
                             - fluid_vol)
        self.bx0 = Constant((0.5*self.length_width[0]
                            - assemble_multimesh(x*dX))/self.Vol0)
        self.by0 = Constant((0.5*self.length_width[1]
                            - assemble_multimesh(y*dX))/self.Vol0)
        print(float(self.Vol0), float(self.bx0), float(self.by0))

    def geometric_quantities(self):
        """
        Compute volume and  barycenter of obstacle, as long as its 
        offset from original values with current multimesh
        """
        x = SpatialCoordinate(self.multimesh)
        V = MultiMeshFunctionSpace(self.multimesh, "CG", 1)
        x = interpolate(Expression("x[0]", degree=1), V)
        y = interpolate(Expression("x[1]", degree=1), V)
        fluid_vol = assemble_multimesh(Constant(1)*dx(domain=self.multimesh) +
                                       Constant(1)*dC(domain=self.multimesh))
        self.Vol = Constant(self.length_width[0]*self.length_width[1]
                             - fluid_vol)
        self.bx = Constant((0.5*self.length_width[0]
                            - assemble_multimesh(x*dX))/self.Vol0)
        self.by = Constant((0.5*self.length_width[1]
                            - assemble_multimesh(y*dX))/self.Vol0)
        self.Voloff = self.Vol - self.Vol0
        self.bxoff = self.bx - self.bx0
        self.byoff = self.by - self.by0


    def recompute_dJ(self):
        """
        Create gradient expression for deformation algorithm
        """
        # FIXME: probably only works with one obstacle
        # Recalculate barycenter and volume of obstacle
        self.geometric_quantities()
        self.integrand_list = []
        dJ = 0
        for i in range(1,self.N):
            # Integrand of gradient
            x = SpatialCoordinate(self.multimesh.part(i))
            u_i = self.u.part(i)
            dJ_stokes = -inner(grad(u_i), grad(u_i))
            dJ_vol = - Constant(2*self.vfac)*(self.Vol-self.Vol0)
            dJ_bar = Constant(2*self.bfac)/self.Vol*((self.bx-x[0])*self.bxoff
                                                     + (self.by-x[1])*self.byoff)
            integrand = dJ_stokes + dJ_vol + dJ_bar
            dDeform = Measure("ds", subdomain_data=self.mfs[i])
            from femorph import VolumeNormal
            n = VolumeNormal(self.multimesh.part(i))
            s = TestFunction(self.S[i])

            self.integrand_list.append(n*integrand)
            dJ += inner(s,n)*integrand*dDeform(self.move_dict[i]["Deform"])
        self.dJ_form = dJ
    
    
    def solve(self):
        """
        Solves the stokes equation with the current multimesh
        """
        (u, p) = TrialFunctions(self.VQ)
        (v, q) = TestFunctions(self.VQ)
        n = FacetNormal(self.multimesh)
        h = 2.0*Circumradius(self.multimesh)
        alpha = Constant(6.0)
        
        tensor_jump = lambda u: outer(u("+"), n("+")) + outer(u("-"), n("-"))

        a_s = inner(grad(u), grad(v))*dX
        a_IP = - inner(avg(grad(u)), tensor_jump(v))*dI\
               - inner(avg(grad(v)), tensor_jump(u))*dI\
               + alpha/avg(h) * inner(jump(u), jump(v))*dI
        a_O = inner(jump(grad(u)), jump(grad(v)))*dO

        b_s = -div(u)*q*dX - div(v)*p*dX
        b_IP = jump(u, n)*avg(q)*dI + jump(v, n)*avg(p)*dI
        l_s = inner(self.f, v)*dX

        s_C = h*h*inner(-div(grad(u)) + grad(p), -div(grad(v)) - grad(q))*dC\
              + h("+")*h("+")*inner(-div(grad(u("+"))) + grad(p("+")),
                                    -div(grad(v("+"))) + grad(q("+")))*dO
        l_C = h*h*inner(self.f, -div(grad(v)) - grad(q))*dC\
              + h("+")*h("+")*inner(self.f("+"),
                                    -div(grad(v("+"))) - grad(q("+")))*dO
        
        a = a_s + a_IP + a_O + b_s + b_IP + s_C
        l = l_s + l_C

        A = assemble_multimesh(a)
        L = assemble_multimesh(l)
        [bc.apply(A, L) for bc in self.bcs]
        self.VQ.lock_inactive_dofs(A, L)
        solve(A, self.w.vector(), L, "mumps")
        self.splitMMF()


    def splitMMF(self):
        """
        Split a mixed multimeshfunction into separate multimeshfunctions
        """
        for i in range(self.multimesh.num_parts()):
            Vi = FunctionSpace(self.multimesh.part(i), self.V2)
            Pi = FunctionSpace(self.multimesh.part(i), self.S1)
            ui, pi = self.w.part(i, deepcopy=True).split()

            self.u.assign_part(i, interpolate(ui,Vi))
            self.p.assign_part(i, interpolate(pi,Pi))

    def save_state(self):
        """
        Save current velocity and pressure to file
        """
        for i in range(self.multimesh.num_parts()):
            self.outu[i] << self.u.part(i,deepcopy=True)
            self.outp[i] << self.p.part(i,deepcopy=True)

    def generate_mesh_deformation(self):
        """
        Generates an linear elastic mesh deformation using the steepest
        gradient as stress on the boundary.
        """
        from Elasticity_solver import ElasticitySolver
        for i in range(1, self.N):
            solver = ElasticitySolver(self.multimesh.part(i), self.mfs[i],
                                      free_marker=self.move_dict[i]["Free"],
                                      deform_marker=self.move_dict[i]["Deform"],
                                      constant_mu=False)
            solver.solve(self.f, -self.integrand_list[i-1])
            plot(solver.u_)
            show()


if __name__ == "__main__":
    meshes = []
    for i in range(2):
        mesh_i = Mesh()
        with XDMFFile("meshes/multimesh_%d.xdmf" %i) as infile:
            infile.read(mesh_i)
        meshes.append(mesh_i)
    mfs = []
    for i in range(2):
        mvc = MeshValueCollection("size_t", meshes[i], 1)
        with XDMFFile("meshes/mf_%d.xdmf" %i) as infile:
            infile.read(mvc, "name_to_read")
        mfs.append(cpp.mesh.MeshFunctionSizet(meshes[i], mvc))

    cover = {0: Point(0.5,0.5)}
    from create_meshes import (inflow, outflow, walls,
                               inner_marker, outer_marker, L, H)
    bc_dict = {0: {inflow: Constant((1.0,0.0)), walls: Constant((1,0))},
               1: {inner_marker: Constant((0,0))}}
    move_dict = {0: {"Fixed": [inflow, outflow, walls]},
                 1: {"Deform": inner_marker,
                     "Free": outer_marker}}
    length_width = [L, H]
    solver = StokesSolver(meshes, mfs, cover, bc_dict, move_dict, length_width)
    solver.solve()
    solver.recompute_dJ()
    solver.generate_mesh_deformation()
