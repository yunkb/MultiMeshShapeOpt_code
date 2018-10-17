from dolfin import *
import matplotlib.pyplot as plt
from IPython import embed
from pdb import set_trace
import numpy
# Verification of functional only consisting of a volume
# that lives on the bottom mesh, where the top mesh is moved.

def convergence_rates(E_values, eps_values):
    from numpy import log
    r = []
    for i in range(1, len(eps_values)):
        r.append(log(E_values[i]/E_values[i-1])/log(eps_values[i]/
                                                    eps_values[i-1]))

    print("Computed convergence rates: {}".format(r))
    return r

# Load meshes and mesh-functions used in the MultiMesh from file
multimesh = MultiMesh()
mfs = []
meshes = []
for i in range(2):
    mesh_i = Mesh()
    with XDMFFile("meshes/multimesh_%d.xdmf" %i) as infile:
        infile.read(mesh_i)
    mvc = MeshValueCollection("size_t", mesh_i, 1)
    with XDMFFile("meshes/mf_%d.xdmf" %i) as infile:
        infile.read(mvc, "name_to_read")
    mfs.append(cpp.mesh.MeshFunctionSizet(mesh_i, mvc))
    meshes.append(mesh_i)
    multimesh.add(mesh_i)

multimesh.build()
multimesh.auto_cover(0,Point(1.25, 0.875))
degree=3
V = MultiMeshFunctionSpace(multimesh, "CG", degree)
mf_0 = mfs[0]
mf_1 = mfs[1]

x0 = SpatialCoordinate(meshes[0])
x1 = SpatialCoordinate(meshes[1])
T = MultiMeshFunction(V)
T.assign_part(0, project(cos(x0[0])*x0[1], FunctionSpace(meshes[0], "CG", degree)))
T.assign_part(1, project(Constant(0), FunctionSpace(meshes[1], "CG", degree)))

def deformation_vector():
    from femorph import VolumeNormal
    n1 = VolumeNormal(multimesh.part(1))
    S_sm = VectorFunctionSpace(multimesh.part(1), "CG", 1)
    bcs = [DirichletBC(S_sm, Constant((0,0)), mfs[1],2),
           DirichletBC(S_sm, n1, mfs[1], 1)]

    u,v = TrialFunction(S_sm), TestFunction(S_sm)
    a = inner(grad(u),grad(v))*dx
    l = inner(Constant((0.,0.)), v)*dx
    n = Function(S_sm)
    solve(a==l, n, bcs=bcs)
    S = MultiMeshVectorFunctionSpace(multimesh, "CG", 1)
    s = MultiMeshFunction(S)
    s.assign_part(1,n)
    return s


# Compute gradient
S = MultiMeshVectorFunctionSpace(multimesh, "CG", 1)
s = TestFunction(S)
n = FacetNormal(multimesh)
def JT(T):
    return inner(grad(T), grad(T))*dX
J = JT(T)

dJdOmega = div(s)*inner(grad(T),grad(T))*dX \
           + 2*inner(grad(dot(s,grad(T))),grad(T))*dX\
           - 2*inner(dot(grad(s), grad(T)), grad(T))*dX
dJds_ = assemble_multimesh(dJdOmega)
s_top = deformation_vector()
s_bottom = MultiMeshFunction(S)

# Project top deformation to bottom mesh
s_b = TrialFunction(S)
# LHS
a = inner(s_b("+"), s("+")) * dI
A = assemble_multimesh(a)
# Make matrix invertible
A.ident_zeros()
# RHS (take top data down to bottom mesh
L = inner(s_top("-"),s("+")) * dI
l = assemble_multimesh(L)
S.lock_inactive_dofs(A,l)
solve(A, s_bottom.vector(), l)

# Compute gradient with bottom mesh vector
dJds = dJds_.inner(s_bottom.vector())
print(dJds)
epsilons = [0.005*0.5**i for i in range(5)]
errors = {"0": [],"1": []}
Js = [assemble_multimesh(J)]

for eps in epsilons:
    # Compute top deformation vector
    s_eps = deformation_vector()

    # Scale movement and deform top mesh
    s_eps.vector()[:] *= eps

    for i in range(2):
        ALE.move(multimesh.part(i), s_eps.part(i))
    multimesh.build()
    multimesh.auto_cover(0,Point(1.25, 0.875))
    J_eps = assemble_multimesh(JT(T))
    Js.append(J_eps)
    errors["0"].append(abs(J_eps-Js[0]))
    errors["1"].append(abs(J_eps-Js[0]-eps*dJds))
    s_eps.vector()[:] *= -1
    for i in range(2):
        ALE.move(multimesh.part(i), s_eps.part(i))
    multimesh.build()
    multimesh.auto_cover(0,Point(1.25, 0.875))
print(errors["0"])
print(errors["1"])
rates0 = convergence_rates(errors["0"], epsilons)
rates1 = convergence_rates(errors["1"], epsilons)
assert(min(rates0)>0.95)
assert(sum(rates1)/len(rates1)>1.95)
print(rates0)
print(rates1)
print(sum(rates1)/len(rates1))
