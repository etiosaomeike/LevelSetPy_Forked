__all__ = ["shapeSphere"]

__author__ 		= "Lekan Molu"
__copyright__ 	= "2021, Hamilton-Jacobi Analysis in Python"
__credits__  	= "There are None."
__license__ 	= "MIT License"
__maintainer__ 	= "Lekan Molu"
__email__ 		= "patlekno@icloud.com"
__status__ 		= "Completed"


import numpy as np
import logging
from LevelSetPy.Utilities.matlab_utils import *

logger = logging.getLogger(__name__)

def shapeSphere(grid, center=None, radius=1):
    """
      shapeSphere: implicit surface function for a sphere.

        data = shapeSphere(grid, center, radius)

      Creates an implicit surface function (actually signed distance)
        for a sphere.

      Can be used to create circles in 2D or intervals in 1D.


      Input Parameters:

        grid: Grid structure (see processGrid.m for details).

        center: Vector specifying center of sphere.  May be a scalar, in
        which case the scalar is multiplied by a vector of ones of the
        appropriate length.  Defaults to 0 (eg centered at the origin).

        radius: Scalar specifying the radius of the sphere. Defaults to 1.

      Output Parameters:

        data: Output data array (of size grid.size) containing the implicit
        surface function.

     Translated August 2, 2021 | Lekan Molu
    ---------------------------------------------------------------------------
     Default parameter values.
    """

    if not np.any(center):
        center = zeros(grid.dim, 1)
    elif(numel(center) == 1):
        center = center * ones(grid.dim, 1, dtype=np.float64)

    #---------------------------------------------------------------------------
    # Signed distance function calculation.
    data = (grid.xs[0] - center[0])**2
    for i in range(1, grid.dim):
        data += (grid.xs[i] - center[i])**2
    data = np.sqrt(data) - radius

    #---------------------------------------------------------------------------
    # Warn the user if there is no sign change on the grid
    #  (ie there will be no implicit surface to visualize).
    if(np.all(data.flatten() < 0) or (np.all(data.flatten() > 0))):
        logger.warn(f'Implicit surface not visible because function has '
                'single sign on grid')
    return data
