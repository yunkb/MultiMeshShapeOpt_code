import numpy

lmb_metal = [429,312,205,205,205]
lmb_insulation = [0.03,0.12,0.06,0.04,0.02]
lmb_fill = 0.33 
c1 = numpy.array([0, 0.6])
c2 = numpy.array([-0.4, 0.2])
c3 = numpy.array([-0.1, -0.4])
c4 = numpy.array([0.6, 0.4])
c5 = numpy.array([0.45, -0.45])

cable_positions = numpy.array([c1[0],c1[1],c2[0],c2[1],c3[0],c3[1],
                               c4[0],c4[1],c5[0],c5[1]])

scales = numpy.array([1,0.75,0.9,1,0.8])   
sources = numpy.array([1,0.5,0.25,0.125,0.0625])

from MultiCable import *
from IpoptMultiCableSolver import *

MC = MultiCable(scales, cable_positions, lmb_metal, lmb_insulation,
                      lmb_fill, sources)
from dolfin import plot, File
outputs = [File("output/fivecables%d.pvd" %i)
           for i in range(MC.multimesh.num_parts())]
MC.eval_J(cable_positions)
for i in range(MC.multimesh.num_parts()):
    outputs[i] << MC.T.part(i)

n_cables = MC.multimesh.num_parts()-1
opt = MultiCableOptimization(n_cables, scales, MC.eval_J, MC.eval_dJ)
opt.nlp.int_option('max_iter', 50)
opt.nlp.num_option('tol', 1e-8)

opt_sol = opt.solve(cable_positions)

MC.eval_J(opt_sol)
for i in range(n_cables):
    print("%.8f, %.8f" %(opt_sol[2*i], opt_sol[2*i+1]))
        
for i in range(MC.multimesh.num_parts()):
    outputs[i] << MC.T.part(i)
