__comment__     = "Solves the BRT of a P-E Dubins Vehicle in Relative Coordinates (Air3D Basic)."
__author__ 		= "Lekan Molu"
__copyright__ 	= "2022, Hamilton-Jacobi Analysis in Python"
__license__ 	= "MIT License"
__comment__ 	= "Evader at origin"
__maintainer__ 	= "Lekan Molu"
__email__ 		= "patlekno@icloud.com"
__status__ 		= "Completed"
__date__ 		= "Nov. 2021"

import copy
import time
import logging
import argparse
import sys, os
import cupy as cp
import numpy  as np
from math import pi
import matplotlib.pyplot as plt
import matplotlib.Gridspec as Gridspec
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from skimage import measure

from os.path import abspath, join, expanduser

from LevelSetPy.Utilities import *
from LevelSetPy.Visualization import *
from LevelSetPy.Grids import createGrid
from LevelSetPy.DynamicalSystems import DubinsVehicleRel
from LevelSetPy.InitialConditions import shapeCylinder
from LevelSetPy.SpatialDerivative import upwindFirstENO2
from LevelSetPy.ExplicitIntegration.Integration import odeCFL2, odeCFLset
from LevelSetPy.ExplicitIntegration.Dissipation import artificialDissipationGLF
from LevelSetPy.ExplicitIntegration.Term import termRestrictUpdate, termLaxFriedrichs

parser = argparse.ArgumentParser(description='Hamilton-Jacobi Analysis')
parser.add_argument('--silent', '-si', action='store_false', help='silent debug print outs' )
parser.add_argument('--save', '-sv', action='store_false', help='save BRS/BRT at end of sim' )
parser.add_argument('--visualize', '-vz', action='store_false', help='visualize level sets?' )
parser.add_argument('--load_brt', '-lb', action='store_true', help='load saved brt?' )
parser.add_argument('--stochastic', '-st', action='store_true', help='Run trajectories with stochastic dynamics?' )
parser.add_argument('--compute_traj', '-ct', action='store_false', help='Run trajectories with stochastic dynamics?' )
parser.add_argument('--verify', '-vf', action='store_true', default=True, help='visualize level sets?' )
parser.add_argument('--elevation', '-el', type=float, default=5., help='elevation angle for target set plot.' )
parser.add_argument('--direction', '-dr',  action='store_true',  help='direction to grow the level sets. Negative by default.' )
parser.add_argument('--azimuth', '-az', type=float, default=15., help='azimuth angle for target set plot.' )
parser.add_argument('--pause_time', '-pz', type=float, default=.3, help='pause time between successive updates of plots' )
args = parser.parse_args()
args.verbose = True if not args.silent else False

print(f'args:  {args}')

if not args.silent:
	logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
else:
	logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
# Turn off pyplot's spurious dumps on screen
logging.getLogger('matplotlib.font_manager').disabled = True
logger = logging.getLogger(__name__)

u_bound = 1
w_bound = 1
fontdict = {'fontsize':16, 'fontweight':'bold'}

def preprocessing():
	global u_bound, w_bound

	grid_min = expand(np.array((-.75, -1.25, -pi)), ax = 1)
	grid_max = expand(np.array((3.25, 1.25, pi)), ax = 1)
	pdDims = 2                      # 3rd dimension is periodic
	resolution = 100
	N = np.array(([[
					resolution,
					np.ceil(resolution*(grid_max[1, 0] - grid_min[1, 0])/ \
								(grid_max[0, 0] - grid_min[0, 0])),
					resolution-1
					]])).T.astype(int)
	grid_max[2, 0] *= (1-2/N[2,0])
	g = createGrid(grid_min, grid_max, N, pdDims)

	#use grid's dx to create tons of trajectories which we shall use to sweep
	# the value function over the whole state space.

	return g, value_init

def main(args):
	# global params
	g, value_init = preprocessing()
	dubins_rel = DubinsVehicleRel(g, u_bound, w_bound)

	# after creating value function, make state space cupy objects
	g.xs = [cp.asarray(x) for x in g.xs]
	finite_diff_data = Bundle(dict(innerFunc = termLaxFriedrichs,
				innerData = Bundle({'grid':g,
					'hamFunc': dubins_rel.hamiltonian,
					'partialFunc': dubins_rel.dissipation,
					'dissFunc': artificialDissipationGLF,
					'CoStateCalc': upwindFirstENO2,
					}),
					positive = args.direction,  # direction to grow the updated level set
				))

	t_range = [0, 2.5]

	# Visualization paramters
	spacing = tuple(g.dx.flatten().tolist())
	init_mesh = implicit_mesh(value_init, level=0, spacing=spacing, edge_color='b', face_color='b')
	params = Bundle(
					{"grid": g,
					 'disp': True,
					 'labelsize': 16,
					 'labels': "Initial 0-LevelSet",
					 'linewidth': 2,
					 'data': value_init,
					 'elevation': args.elevation,
					 'azimuth': args.azimuth,
					 'mesh': init_mesh,
					 'init_conditions': False,
					 'pause_time': args.pause_time,
					 'level': 0, # which level set to visualize
					 'winsize': (16,9),
					 'fontdict': Bundle({'fontsize':18, 'fontweight':'bold'}),
					 "savedict": Bundle({"save": False,
									"savename": "dint_basic.jpg",
									"savepath": join(expanduser("~"),
									"Documents/Papers/Safety/PGDReach/figures")
								 })
					})
	args.spacing = spacing
	args.init_mesh = init_mesh; args.params = params

	if args.load_brt:
		args.save = False
		brt = np.load("data/rcbrt.npz")
	else:
		if args.visualize:
			viz = RCBRTVisualizer(params=args.params)
		t_plot = (t_range[1] - t_range[0]) / 10
		small = 100*eps
		options = Bundle(dict(factorCFL=0.95, stats='on', singleStep='off'))

		# Loop through t_range (subject to a little roundoff).
		t_now = t_range[0]
		start_time = cputime()
		itr_start = cp.cuda.Event()
		itr_end = cp.cuda.Event()

		brt = [value_init]
		meshes, brt_time = [], []
		value_rolling = cp.asarray(copy.copy(value_init))

		while(t_range[1] - t_now > small * t_range[1]):
			itr_start.record()
			cpu_start = cputime()
			time_step = f"{t_now}/{t_range[-1]}"

			# Reshape data array into column vector for ode solver call.
			y0 = value_rolling.flatten()

			# How far to step?
			t_span = np.hstack([ t_now, min(t_range[1], t_now + t_plot) ])

			# Integrate a timestep.
			t, y, _ = odeCFL2(termRestrictUpdate, t_span, y0, odeCFLset(options), finite_diff_data)
			cp.cuda.Stream.null.synchronize()
			t_now = t

			# Get back the correctly shaped data array
			value_rolling = y.reshape(g.shape)

			if args.visualize:
				value_rolling_np = value_rolling.get()
				mesh=implicit_mesh(value_rolling_np, level=0, spacing=args.spacing,
									edge_color=None,  face_color='maroon')
				viz.update_tube(mesh, time_step, True)
				# store this brt
				brt.append(value_rolling_np); brt_time.append(t_now); meshes.append(mesh)

			if args.save:
				fig = plt.gcf()
				fig.savefig(join(expanduser("~"),"Documents/Papers/Safety/WAFR2022",
					rf"figures/rcbrt_{t_now}.jpg"),
					bbox_inches='tight',facecolor='None')

			itr_end.record()
			itr_end.synchronize()
			cpu_end = cputime()

			info(f't: {time_step} | GPU time: {(cp.cuda.get_elapsed_time(itr_start, itr_end)):.2f} | CPU Time: {(cpu_end-cpu_start):.2f}, | Targ bnds {min(y):.2f}/{max(y):.2f} Norm: {np.linalg.norm(y, 2):.2f}')

		if not args.load_brt:
			os.makedirs("data") if not os.path.exists("data") else None
			np.savez_compressed("data/rcbrt.npz", brt=np.asarray(brt), \
				meshes=np.asarray(meshes), brt_time=np.asarray(brt_time))

	if args.verify:
		x0 = np.array([[1.25, 0, pi]])

		#examine to see if the initial state is in the BRS/BRT
		gexam = copy.deepcopy(g)

if __name__ == '__main__':
	main(args)
