from proteus.mprans.BodyDynamics import RigidBody
import numpy as np
from proteus import (Domain,
                    Context,
                    WaveTools as wt,
                    Gauges as ga,
                    MeshTools as mt, 
                    AuxiliaryVariables)
from proteus.mprans import SpatialTools as st
from proteus.ctransportCoefficients import (smoothedHeaviside,
                                            smoothedHeaviside_integral)
from proteus.Profiling import logEvent
from proteus.mprans.SpatialTools import Tank2D
from proteus.mprans import BodyDynamics as bd
import proteus.TwoPhaseFlow.TwoPhaseFlowProblem as TpFlow


# --- Context Options

opts=Context.Options([

    # Air/Water Physical Parameters
    ("rho_0",998.2,"water density"),
    ("nu_0",1.004e-6,"water viscosity"),
    ("rho_1",1.205,"air density"),
    ("nu_1",1.500e-5,"air viscosity"),
    ("g",np.array([0,-9.81,0]), "Gravity vector in m/s^2"),

    # Tank Geometry
    ("water_level", 0.9,"Height of free surface above bottom"),
    ("tank_dim", (1., 1.5,), "Dimensions of the tank"),
    ("tank_sponge", (1., 1.), "Length of relaxation zones (front/back, left/right)"),
    ("tank_BC",'FreeSlip', "tank boundary conditions: NoSlip or FreeSlip"),

    # Wave Characteristics
    ("waveType",'Linear' ,"Fenton"),
    ("T", 1., "Period of the waves in s"),
    ("wave_height", 0.1, "Height of the waves in m"),
    ("depth", 0.9, "Wave depth in m"),
    ("waveDir", np.array([1., 0., 0.]), "Direction of the waves (from left boundary)"),
    ("Nf",8,"Fenton Fourier Components"),
    ("ecH",3.,"Smoothing Coefficient"),
    ("wave", True, "Enable Generation"),
 
   # Caisson
    ("caisson2D", True, "Switch on/off caisson2D"),
    ("center", (0.5, 0.9),"Coord of the caisson center"),
    ("dim",(0.3,0.3),"(X-dimension of the caisson2D,Y-dimension of the caisson2D"),
    ('width', 0.9, 'Z-dimension of the caisson2D'),
    ('mass', 30., 'Mass of the caisson2D [kg]'),#125
    ('caisson_BC', 'FreeSlip', 'caisson2D boundaries: NoSlip or FreeSlip'),
    ("free_x", np.array([0., 0.0, 0.0]), "Translational DOFs"),
    ("free_r", np.array([0., 0., 1.0]), "Rotational DOFs"),
    ("caisson_inertia", 0.236, "Inertia of the caisson 0.236, 1.04 [kg m2]"),
    ("rotation_angle", 0., "Initial rotation angle (in degrees)"),
    ("Tn", 0.93, "Roll natural period"),
    ("overturning", True, "Switch on/off overturning module"),
    
    # Numerical Settings & Parameters
    ("he", 0.06,"maximum element edge length"),
    ("cfl", 0.4,"Target cfl"),
    ("duration", 10., "Duration of the simulation"),
    ("Tend", 1000, "Simulation time in s"),
    ("Np", 30 ," Output points per period Tp/Np"),
    ("dt_init",0.001,"initial time step"),
    ("sigma_01", 0.,"surface tension"),
    ('movingDomain', True, "Moving domain and mesh option"),
    ('scheme', 'Forward_Euler', 'Numerical scheme applied to solve motion calculation (Runge_Kutta or Forward_Euler)'),
    ])

###################     Fluid Domain         ###################
domain = Domain.PlanarStraightLineGraphDomain()

# --- Wave input
wave = wt.MonochromaticWaves(period=opts.T,
                            waveHeight=opts.wave_height,
                            mwl=opts.water_level,
                            depth=opts.depth,
                            g=opts.g,
                            waveDir=opts.waveDir,
			    waveType=opts.waveType, 
			    autoFenton=True, 
			    Nf=opts.Nf)
                            
wave_length=wave.wavelength

# --- Tank Setup
tank = st.Tank2D(domain, opts.tank_dim)

###################	Body Domain	###################

# ---  Caisson2D Geometry / Shapes
xc1 = opts.center[0]-0.5*opts.dim[0]
yc1 = opts.center[1]-0.5*opts.dim[1]
xc2 = xc1+opts.dim[0]
yc2 = yc1
xc3 = xc2
yc3 = yc2+opts.dim[1]
xc4 = xc1
yc4 = yc3

# --- Caisson2D Properties
if opts.caisson2D:
    VCG = opts.dim[1]/2.
    volume = float(opts.dim[0]*opts.dim[1]*opts.width)
    density = float(opts.mass/volume)
    inertia = opts.caisson_inertia/opts.mass/opts.width

# --- Shape properties setup
    caisson = st.Rectangle(domain, dim=opts.dim, coords=opts.center)
    xc1, yc1 = caisson.vertices[0][0], caisson.vertices[0][1]
    xc2, yc2 = caisson.vertices[1][0], caisson.vertices[1][1]

# --- Body properties setup
    #caisson2D = bd.RigidBody(shape=caisson, substeps=20)
    caisson2D = bd.CaissonBody(shape=caisson, substeps=40)
    caisson2D.setMass(mass=opts.mass)
    caisson2D.setConstraints(free_x=opts.free_x, free_r=opts.free_r)
    rotation = np.radians(opts.rotation_angle)
    caisson.rotate(rotation)
    caisson2D.It = inertia
    caisson2D.setNumericalScheme(scheme=opts.scheme)
    caisson2D.setRecordValues(filename='caisson2D', all_values=True)


# --- Caisson2D
for bc in caisson.BC_list:
    if opts.caisson_BC == 'NoSlip':
        bc.setNoSlip()
    if opts.caisson_BC == 'FreeSlip':
        bc.setFreeSlip()

def prescribed_motion(t):
        new_x = np.array(opts.dim)
        new_x[1] = opts.dim[1]+0.01*cos(2*np.pi*(t/4)+np.pi/2)
        return new_x

###################	Boundary Conditions	###################

ecH=opts.ecH
smoothing=opts.ecH*opts.he

boundaryTags = {'y-' : 1,
                'x+' : 2,
                'y+' : 3,
                'x-' : 5,
                'sponge' : 5,
                'porousLayer' : 6,
                'moving_porousLayer' : 7,
               }

tank.BC['x-'].setUnsteadyTwoPhaseVelocityInlet(wave=wave, smoothing=smoothing, vert_axis=1)
tank.BC['y+'].setAtmosphere() 
tank.BC['y-'].setFreeSlip()
tank.BC['x+'].setFreeSlip()
tank.BC['sponge'].setNonMaterial()

tank.BC['x-'].setFixedNodes()
tank.BC['x+'].setFixedNodes()
tank.BC['sponge'].setFixedNodes()
tank.BC['y+'].setTank() #Allows nodes to slip freely
tank.BC['y-'].setTank() #Allows nodes to slip freely

###################	Generation & Absorption Zone	###################

dragAlpha = 5*(2*np.pi/opts.T)
tank.setSponge(x_n=opts.tank_sponge[0]*wave_length, x_p=opts.tank_sponge[1]*wave_length)
tank.setGenerationZones(x_n=True, waves=wave, smoothing=smoothing, dragAlpha=dragAlpha)
tank.setAbsorptionZones(x_p=True, dragAlpha=dragAlpha) 

if opts.caisson2D:
    tank.setChildShape(caisson, 0)

# --- Assemble Domain                                                                                                                                                                                                                                                 
domain.MeshOptions.he = opts.he
st.assembleDomain(domain)

###################	Initial Conditions	###################

def signedDistance(x):
    return x[1] - opts.water_level

class P_IC:
    def __init__(self):
        self.mwl=opts.water_level
    def uOfXT(self,x,t):
        if signedDistance(x) < 0:
            return -(opts.tank_dim[1] - opts.water_level)*opts.rho_1*opts.g[1] - (opts.water_level - x[1])*opts.rho_0*opts.g[1]
        else:
            return -(opts.tank_dim[1] - opts.water_level)*opts.rho_1*opts.g[1]
class AtRest:
    def uOfXT(self, x, t):
        return 0.0
class VOF_IC:
    def uOfXT(self,x,t):
        return smoothedHeaviside(opts.ecH*opts.he, signedDistance(x))

class LS_IC:
    def uOfXT(self,x,t):
        return signedDistance(x)

initialConditions = {'pressure': P_IC(),
                     'vel_u': AtRest(),
                     'vel_v': AtRest(),
                     'vel_w': AtRest(),
                     'vof': VOF_IC(),
                     'ncls': LS_IC(),
                     'rdls': LS_IC(),}

###################     Time step controls      ################### 
dt_output = opts.T/opts.Np
outputStepping = TpFlow.OutputStepping(final_time=opts.duration,
                                       dt_init=opts.dt_init,
                                       dt_output=dt_output,
                                       nDTout=None,
                                       dt_fixed=None)

myTpFlowProblem = TpFlow.TwoPhaseFlowProblem(ns_model=0,
                                             ls_model=0,
                                             nd=domain.nd,
                                             cfl=opts.cfl,
                                             outputStepping=outputStepping,
                                             he=opts.he,
                                             domain=domain,
                                             initialConditions=initialConditions)

# --- Physical Parameters for Two Phase Flow

params = myTpFlowProblem.Parameters
myTpFlowProblem.useSuperLu=False#True
params.physical.surf_tension_coeff = opts.sigma_01

# ---  index in order of
m = params.Models
m.rdls.p.CoefficientsOptions.epsFact=0.75

m.moveMeshElastic.index=0
m.rans2p.index = 1
m.vof.index = 2
m.ncls.index = 3
m.rdls.index = 4
m.mcorr.index = 5

myTpFlowProblem.Parameters.Models.rans2p.auxiliaryVariables += domain.auxiliaryVariables['twp']
