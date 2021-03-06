from dolfin import * # Only here to give pyipopt the correct petsc_comm_world
import numpy
import pyipopt
import sympy


class MultiCableOptimization():
    
    def __init__(self, num_cables, cable_scales, J, dJ):      
        self.g_scale = 1 # Scaling of coefficient for gradient constraint
        self.outer_radius = 1.2 # Radius of background cable
        self.inner_radius = 0.3 # Radius for each inner cable
        self.distance_from_outer = 0.05 # Distance for each cable to outer boundary
        self.distance_from_internal = 0.025 # Distance between each internal cable
        self.num_cables = num_cables
        self.inner_radius *= cable_scales
        self.max_radius = self.outer_radius - self.inner_radius\
                          - self.distance_from_outer
        self.sympy_g(self.num_cables)
        self.sympy_jac_g()
        self.solve_init(J, dJ)

    def eval_g(self, x):
        """ Evaluate inequality constraint, g(x) <= 0, """
        return self.replace_sympy_g(x)


    def eval_jac_g(self, cable_positions, flag):
        """ The constraint Jacobian:
        flag = True  means 'tell me the sparsity pattern';
        flag = False means 'give me the Jacobian'.
        """
        if flag:
            # FIXME: Pass in a dense matrix
            # (could be optimised, but we don't care for this small problem).
            nvar = len(cable_positions)
            n_cables = int(nvar/2)
            ncon = int(n_cables + n_cables*(n_cables-1)/2)
            rows = []
            for i in range(ncon):
                rows += [i] * nvar
            cols = list(range(nvar)) * ncon
            return (numpy.array(rows), numpy.array(cols))
        else:
            return self.replace_sympy_jac_g(cable_positions)

    
    def sympy_g(self, num_cables):
        """ Creates the maximum distance and no-collision constraint 
        for each sub-cables with sympy, returning the g in inequality g<=0 and
        an array z of the control variables
        """
        x = list(sympy.symbols("x0:%d" % num_cables))
        y = list(sympy.symbols("y0:%d" % num_cables))
        g,z= [],[]
        for i in range(num_cables):
            g.append(x[i]**2 + y[i]**2 - self.max_radius[i]**2)
        for i in range(num_cables):
            z.append(x[i])
            z.append(y[i])
            for j in range(i+1,num_cables):
                xi, yi = x[i], y[i]
                xj, yj = x[j], y[j]
                int_radius = self.inner_radius[i] + self.inner_radius[j]\
                             + self.distance_from_internal
                # FIXME: Max_int_radius should change with each cable radius
                g.append(int_radius**2 - (xi - xj)**2 - (yi - yj)**2)
        self.g = sympy.Matrix(g)
        self.z = sympy.Matrix(z)
    

    def sympy_jac_g(self):
        """ Creates jacobian for constraints """
        self.jac_g = self.g.jacobian(self.z)


    def replace_sympy_g(self, positions):
        """ Create numpy array of constraint at current positions """
        g_numpy = self.g.subs([(self.z[i], positions[i])
                               for i in range(2*self.num_cables)])
        return self.g_scale*numpy.array(g_numpy).astype(float)


    def replace_sympy_jac_g(self, positions):
        """ Create numpy array of jacobian of constraint at
        current positions """    
        numpy_jac_g = self.jac_g.subs([(self.z[i], positions[i])
                                       for i in range(2*self.num_cables)])
        return self.g_scale*numpy.array(numpy_jac_g).astype(float)

    def solve_init(self, eval_J, eval_dJ):
        nvar = int(2*self.num_cables)
        ncon = int(self.num_cables + self.num_cables*(self.num_cables-1)/2)
        low_var = -numpy.inf*numpy.ones(nvar,dtype=float)
        up_var = numpy.inf*numpy.ones(nvar, dtype=float)
        up_var[0], low_var[0] = 0, 0
        inf_con = numpy.inf*numpy.ones(ncon, dtype=float)
        zero_con = numpy.zeros(ncon, dtype=float)
        self.nlp = pyipopt.create(nvar,      # Number of controls
                                  low_var,  # Lower bounds for Control
                                  up_var,   # Upper bounds for Control
                                  ncon,      # Number of constraints
                                  -inf_con,  # Lower bounds for contraints
                                  zero_con,   # Upper bounds for contraints
                                  nvar*ncon, # Number of nonzeros in cons. Jac
                                  0,         # Number of nonzeros in cons. Hes
                                  lambda pos: eval_J(pos),  # Objective eval
                                  lambda pos: eval_dJ(pos), # Obj. grad eval
                                  self.eval_g,    # Constraint evaluation
                                  self.eval_jac_g # Constraint Jacobian evaluation
        )
         # So it does not violate the boundary constraint
        self.nlp.num_option('bound_relax_factor', 0)
        self.nlp.int_option('print_level', 6)

    def solve(self, cable_positions):
        return self.nlp.solve(cable_positions)[0]
