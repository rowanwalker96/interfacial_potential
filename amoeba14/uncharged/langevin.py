#!/usr/bin/env python3

from simtk.openmm.app import *
from simtk.openmm import *
from simtk.unit import *
from sys import stdout
import numpy as np

platform = Platform.getPlatformByName('CUDA') 

sys = PDBFile('SYSTEM.pdb')
forcefield = ForceField('amoeba2013_wm2014_00enm2.xml') # please make sure to use 2014watermodel
print('Constructing sytem')
system = forcefield.createSystem(sys.topology,nonbondedMethod=PME, nonbondedCutoff=1*nanometer,
        ewaldErrorTolerance=0.00001, vdwCutoff=1.2*nanometer, polarization='mutual', 
        mutualInducedTargetEpsilon=1e-5, constraints=None, rigidWater=False,removeCMMotion=True )

multipole_force = [ f for f in system.getForces() if isinstance(f, AmoebaMultipoleForce)][0]
get_atomic_charges = np.vectorize(lambda index: multipole_force.getMultipoleParameters(int(index))[0].value_in_unit(elementary_charge))

# add the slab geometry 3dc correction
# assume charge neutral system. sum(q) = 0
muz = CustomExternalForce('q*z')
muz.addPerParticleParameter('q')

for i in range(system.getNumParticles()):
    q = get_atomic_charges([i])[0] 
    muz.addParticle(i, [q]) # adding the particles to the force, with perparticle parameters
    
box = system.getDefaultPeriodicBoxVectors()
vol = (box[0][0] * box[1][1] * box[2][2]).value_in_unit(nanometer ** 3)  # assume rectangular box
    
cvforce = CustomCVForce('k*muz*muz')
_conv = (1.602E-19) ** 2 / 1E-9 / (4 * 3.1415926) / 8.854E-12 * 6.022E23 / 1000  # convert from e^2/nm to kJ/mol
cvforce.addGlobalParameter('k', 2 * 3.1415926 / vol * _conv)
cvforce.addCollectiveVariable('muz', muz)
system.addForce(cvforce)   

integrator = LangevinIntegrator(300*kelvin, 1/picosecond, 0.001*picoseconds)
#integrator = VariableLangevinIntegrator(300*kelvin, 1/picosecond, 0.001) # multiple timestep langevin
simulation = Simulation(sys.topology, system, integrator, platform)
simulation.context.setPositions(sys.positions)

print("--> performing energy minimsation")
simulation.minimizeEnergy(1*kilojoule_per_mole)

simulation.context.setVelocitiesToTemperature(300*kelvin)

# set timestamps
mdsteps =  1100000 # 1.1ns at 1 fs timestep
dcdperiod =   100  #  ps at 1 fs timestep
logperiod =   5000 #  ps at 1 fs timestep
checkpoint_steps = 5000


print('Setting reporters') 
simulation.reporters.append(StateDataReporter('md.log', logperiod, step=True,
 time=True, potentialEnergy=True, kineticEnergy=True, totalEnergy=True,
 temperature=True, progress=True, volume=True, density=True,
 remainingTime=True, speed=True, totalSteps=mdsteps, separator='\t'))
simulation.reporters.append(DCDReporter('md.dcd', dcdperiod))
#simulation.reporters.append(StateDataReporter('data.csv', 100, time=True, temperature=True, potentialEnergy=True))

simulation.reporters.append(CheckpointReporter('md.chk',checkpoint_steps))

print('Running MD') 

simulation.step(mdsteps)


simulation.saveState('md.xml')
positions = simulation.context.getState(getPositions=True).getPositions()
PDBFile.writeFile(simulation.topology, positions, open('md.pdb', 'w'))
