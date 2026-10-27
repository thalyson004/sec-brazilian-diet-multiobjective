"""SPEA2 normalization with a defined scale for constant coordinates."""
import numpy as np
from pymoo.algorithms.moo.nsga3 import HyperplaneNormalization
from pymoo.algorithms.moo.spea2 import SPEA2Survival


class ConstantCoordinateNormalization(HyperplaneNormalization):
    def update(self, F, nds=None):
        super().update(F, nds=nds)
        span=self.nadir_point-self.ideal_point
        # A constant coordinate carries no distance information. A unit
        # divisor maps its zero numerator to zero while preserving all
        # positive-span coordinates and the original strength calculation.
        constant=span<=0.
        self.nadir_point[constant]=self.ideal_point[constant]+1.


class StableSPEA2Survival(SPEA2Survival):
    def __init__(self):
        super().__init__(normalize=True)

    def _do(self, problem, pop, *args, **kwargs):
        if self.norm is None:
            self.norm=ConstantCoordinateNormalization(pop.get('F').shape[1])
        result=super()._do(problem,pop,*args,**kwargs)
        for field in ('SPEA_F','SPEA_D','SPEA_R'):
            if not np.isfinite(pop.get(field)).all():
                raise ValueError(f'Nonfinite SPEA2 internal {field}')
        return result
