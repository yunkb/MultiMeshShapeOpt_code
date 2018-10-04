from dolfin import *
from IPython import embed
import numpy
import pyipopt
import sympy


class IpoptAngle():
    
    def __init__(self, num_angles, J, dJ):
        self.num_angles = num_angles
        self.solve_init(J, dJ)

    def func_g(self, x, user_data=None):
        return empty

    def jac_g(self, x, flag, user_data=None):
        if flag:
            rows = numpy.array([], dtype=int)
            cols = numpy.array([], dtype=int)
            return (rows, cols)
        else:
            empty = numpy.array([], dtype=float)
            return empty

        
    def solve_init(self, eval_J, eval_dJ):
        nvar = self.num_angles
        low_var = -360*numpy.ones(nvar,dtype=float)
        up_var = 360*numpy.ones(nvar, dtype=float)


        self.nlp = pyipopt.create(nvar,     # Number of controls
                                  low_var,  # Lower bounds for Control
                                  up_var,   # Upper bounds for Control
                                  0,     # Number of constraints
                                  numpy.array([], dtype=float),
                                  numpy.array([], dtype=float),
                                  0,        # Number of nonzeros in cons. Jac
                                  0,        # Number of nonzeros in cons. Hes
                                  lambda angle: eval_J(angle),  # Objective eval
                                  lambda angle: eval_dJ(angle), # Obj. grad eval
                                  self.func_g,
                                  self.jac_g)
        self.nlp.num_option('bound_relax_factor', 0)

    def solve(self, angle):
        return self.nlp.solve(angle)[0]


if __name__ == "__main__":
    from StokesSolver import *
    points = [Point(0.5,0.5)]#[Point(0.5,0.25), Point(0.75,0.52), Point(0.3,0.8)]
    thetas = numpy.array([0], dtype=float)#[90, 47, 32]
    inlet_str= "-A*(x[1]-x_l)*(x[1]-x_u)"
    inlet_data = [[Expression((inlet_str, "0"), x_l=0.1, x_u=0.4,
                                     A=250, degree=5), 1],
                         [Expression((inlet_str, "0"), x_l=0.7, x_u=0.85,
                                     A=0, degree=5), 2]]

    pre = "meshes/"
    meshes = [pre+"multimesh_0.xdmf"] +  [pre+"multimesh_1.xdmf"]*len(points)
    mfs = [pre+"mf_0.xdmf"] + [pre+"mf_1.xdmf"]*len(points)
    solver = StokesSolver(points, thetas, meshes, mfs, inlet_data)
    # Save initial solution
    solver.eval_J(thetas)
    solver.save_state()
    optimizer = IpoptAngle(len(thetas),solver.eval_J, solver.eval_dJ)
    optimizer.nlp.int_option('max_iter',30)
    optimizer.nlp.num_option("tol", 1e-6)
    opt_theta = optimizer.solve(thetas)

    print(opt_theta, solver.eval_J(opt_theta))
    # solve_final solution
    solver.save_state()
