# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
Module to test fitting routines
"""

from __future__ import (absolute_import, unicode_literals, division,
                        print_function)

import os.path

import numpy as np

from numpy import linalg
from numpy.testing.utils import assert_allclose, assert_almost_equal

from . import irafutil
from .. import models
from .. import fitting
from ..core import Fittable2DModel, Parameter
from ..fitting import LevMarLSQFitter, SimplexLSQFitter, SLSQPLSQFitter
from ...utils import NumpyRNGContext
from ...utils.data import get_pkg_data_filename
from ...tests.helper import pytest

try:
    from scipy import optimize
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


fitters = [SimplexLSQFitter, SLSQPLSQFitter]


class TestPolynomial2D(object):
    """Tests for 2D polynomail fitting."""

    def setup_class(self):
        self.model = models.Polynomial2D(2)
        self.y, self.x = np.mgrid[:5, :5]

        def poly2(x, y):
            return 1 + 2 * x + 3 * x ** 2 + 4 * y + 5 * y ** 2 + 6 * x * y
        self.z = poly2(self.x, self.y)
        self.fitter = fitting.LinearLSQFitter()

    def test_poly2D_fitting(self):
        v = self.model.fit_deriv(x=self.x, y=self.y)
        p = linalg.lstsq(v, self.z.flatten())[0]
        new_model = self.fitter(self.model, self.x, self.y, self.z)
        assert_allclose(new_model.parameters, p)

    def test_eval(self):
        new_model = self.fitter(self.model, self.x, self.y, self.z)
        assert_allclose(new_model(self.x, self.y), self.z)

    @pytest.mark.skipif('not HAS_SCIPY')
    def test_polynomial2D_nonlinear_fitting(self):
        self.model.parameters = [.6, 1.8, 2.9, 3.7, 4.9, 6.7]
        nlfitter = fitting.LevMarLSQFitter()
        new_model = nlfitter(self.model, self.x, self.y, self.z)
        assert_allclose(new_model.parameters, [1, 2, 3, 4, 5, 6])


class TestICheb2D(object):
    """
    Tests 2D Chebyshev polynomial fitting

    Create a 2D polynomial (z) using Polynomial2DModel and default coefficients
    Fit z using a ICheb2D model
    Evaluate the ICheb2D polynomial and compare with the initial z
    """

    def setup_class(self):
        self.pmodel = models.Polynomial2D(2)
        self.y, self.x = np.mgrid[:5, :5]
        self.z = self.pmodel(self.x, self.y)
        self.cheb2 = models.Chebyshev2D(2, 2)
        self.fitter = fitting.LinearLSQFitter()

    def test_default_params(self):
        self.cheb2.parameters = np.arange(9)
        p = np.array([1344., 1772., 400., 1860., 2448., 552., 432., 568.,
                      128.])
        z = self.cheb2(self.x, self.y)
        model = self.fitter(self.cheb2, self.x, self.y, z)
        assert_almost_equal(model.parameters, p)

    def test_poly2D_cheb2D(self):
        model = self.fitter(self.cheb2, self.x, self.y, self.z)
        z1 = model(self.x, self.y)
        assert_almost_equal(self.z, z1)

    @pytest.mark.skipif('not HAS_SCIPY')
    def test_chebyshev2D_nonlinear_fitting(self):
        cheb2d = models.Chebyshev2D(2, 2)
        cheb2d.parameters = np.arange(9)
        z = cheb2d(self.x, self.y)
        cheb2d.parameters = [0.1, .6, 1.8, 2.9, 3.7, 4.9, 6.7, 7.5, 8.9]
        nlfitter = fitting.LevMarLSQFitter()
        model = nlfitter(cheb2d, self.x, self.y, z)
        assert_allclose(model.parameters, [0, 1, 2, 3, 4, 5, 6, 7, 8],
                        atol=10**-9)


@pytest.mark.skipif('not HAS_SCIPY')
class TestJointFitter(object):

    """
    Tests the joint fitting routine using 2 gaussian models
    """
    def setup_class(self):
        """
        Create 2 gaussian models and some data with noise.
        Create a fitter for the two models keeping the amplitude parameter
        common for the two models.
        """
        self.g1 = models.Gaussian1D(10, mean=14.9, stddev=.3)
        self.g2 = models.Gaussian1D(10, mean=13, stddev=.4)
        self.jf = fitting.JointFitter([self.g1, self.g2],
                                      {self.g1: ['amplitude'],
                                       self.g2: ['amplitude']}, [9.8])
        self.x = np.arange(10, 20, .1)
        y1 = self.g1(self.x)
        y2 = self.g2(self.x)

        with NumpyRNGContext(0x01010101):
            n = np.random.randn(100)

        self.ny1 = y1 + 2 * n
        self.ny2 = y2 + 2 * n
        self.jf(self.x, self.ny1, self.x, self.ny2)

    def test_joint_parameter(self):
        """
        Tests that the amplitude of the two models is the same
        """
        assert_allclose(self.jf.fitparams[0], self.g1.parameters[0])
        assert_allclose(self.jf.fitparams[0], self.g2.parameters[0])

    def test_joint_fitter(self):
        """
        Tests the fitting routine with similar procedure.
        Compares the fitted parameters.
        """
        p1 = [14.9, .3]
        p2 = [13, .4]
        A = 9.8
        p = np.r_[A, p1, p2]

        def model(A, p, x):
            return A * np.exp(-0.5 / p[1] ** 2 * (x - p[0]) ** 2)

        def errfunc(p, x1, y1, x2, y2):
            return np.ravel(np.r_[model(p[0], p[1:3], x1) - y1,
                            model(p[0], p[3:], x2) - y2])

        coeff, _ = optimize.leastsq(errfunc, p,
                                    args=(self.x, self.ny1, self.x, self.ny2))
        assert_allclose(coeff, self.jf.fitparams, rtol=10 ** (-2))


class TestLinearLSQFitter(object):

    def setup_class(self):
        test_file = get_pkg_data_filename(os.path.join('data',
                                                       'idcompspec.fits'))
        f = open(test_file)
        lines = f.read()
        reclist = lines.split('begin')
        f.close()
        record = irafutil.IdentifyRecord(reclist[1])
        self.icoeff = record.coeff
        order = int(record.fields['order'])
        self.model = models.Chebyshev1D(order - 1)
        self.model.domain = record.get_range()
        self.lf = fitting.LinearLSQFitter()
        self.x = record.x
        self.y = record.z
        self.yy = np.array([record.z, record.z])

    def test_chebyshev1D(self):
        new_model = self.lf(self.model, self.x, self.y)
        assert_allclose(new_model.parameters, np.array(self.icoeff),
                        rtol=10E-2)


@pytest.mark.skipif('not HAS_SCIPY')
class TestNonLinearFitters(object):
    """
    Tests non-linear least squares fitting and the SLSQP algorithm
    """

    def setup_class(self):
        self.initial_values = [100, 5, 1]

        self.xdata = np.arange(0, 10, 0.1)
        sigma = 8. * np.ones_like(self.xdata)

        with NumpyRNGContext(0xDEADBEEF):
            yerror = np.random.normal(0, sigma)

        def func(p, x):
            return p[0] * np.exp(-0.5 / p[2] ** 2 * (x - p[1]) ** 2)

        self.ydata = func(self.initial_values, self.xdata) + yerror
        self.gauss = models.Gaussian1D(100, 5, stddev=1)

    def test_estimated_vs_analytic_deriv(self):
        """
        Runs `LevMarLSQFitter` with estimated and analytic derivatives of a
        `Gaussian1D`.
        """

        fitter = fitting.LevMarLSQFitter()
        model = fitter(self.gauss, self.xdata, self.ydata)
        g1e = models.Gaussian1D(100, 5.0, stddev=1)
        efitter = fitting.LevMarLSQFitter()
        emodel = efitter(g1e, self.xdata, self.ydata, estimate_jacobian=True)
        assert_allclose(model.parameters, emodel.parameters, rtol=10 ** (-3))

    @pytest.mark.skipif('not HAS_SCIPY')
    def test_with_optimize(self):
        """
        Tests results from `LevMarLSQFitter` against `scipy.optimize.leastsq`.
        """

        fitter = fitting.LevMarLSQFitter()
        model = fitter(self.gauss, self.xdata, self.ydata,
                       estimate_jacobian=True)

        def func(p, x):
            return p[0] * np.exp(-0.5 / p[2] ** 2 * (x - p[1]) ** 2)

        def errfunc(p, x, y):
            return func(p, x) - y

        result = optimize.leastsq(errfunc, self.initial_values,
                                  args=(self.xdata, self.ydata))
        assert_allclose(model.parameters, result[0], rtol=10 ** (-3))

    @pytest.mark.parametrize('fitter_class', fitters)
    def test_fitter_against_LevMar(self, fitter_class):
        """Tests results from non-linear fitters against `LevMarLSQFitter`."""

        levmar = fitting.LevMarLSQFitter()
        fitter = fitting.SLSQPLSQFitter()
        new_model = fitter(self.gauss, self.xdata, self.ydata)
        model = levmar(self.gauss, self.xdata, self.ydata)
        assert_allclose(model.parameters, new_model.parameters,
                        rtol=10 ** (-4))

    def test_LSQ_SLSQP_with_constraints(self):
        """
        Runs `LevMarLSQFitter` and `SLSQPLSQFitter` on a model with
        constraints.
        """

        g1 = models.Gaussian1D(100, 5, stddev=1)
        g1.mean.fixed = True
        fitter = fitting.LevMarLSQFitter()
        fslsqp = fitting.SLSQPLSQFitter()
        slsqp_model = fslsqp(g1, self.xdata, self.ydata)
        model = fitter(g1, self.xdata, self.ydata)
        assert_allclose(model.parameters, slsqp_model.parameters,
                        rtol=10 ** (-4))

    def test_simplex_lsq_fitter(self):
        """A basic test for the `SimplexLSQ` fitter."""

        class Rosenbrock(Fittable2DModel):
            a = Parameter()
            b = Parameter()

            @staticmethod
            def eval(x, y, a, b):
                return (a - x) ** 2 + b * (y - x ** 2) ** 2

        x = y = np.linspace(-3.0, 3.0, 100)
        with NumpyRNGContext(0xCAFECAFE):
            z = Rosenbrock.eval(x, y, 1.0, 100.0) + np.random.normal(0., 0.1)

        fitter = SimplexLSQFitter()
        r_i = Rosenbrock(1, 100)
        r_f = fitter(r_i, x, y, z)

        assert_allclose(r_f.parameters, [1.0, 100.0], rtol=1e-2)

    def test_param_cov(self):
        """
        Tests that the 'param_cov' fit_info entry gets the right answer for
        *linear* least squares, where the answer is exact
        """

        a = 2
        b = 100

        with NumpyRNGContext(0x1337FACE):
            x = np.linspace(0, 1, 100)
            # y scatter is amplitude ~1 to make sure covarience is
            # non-negligible
            y = x*a + b + np.random.randn(len(x))

        #first compute the ordinary least squares covariance matrix
        X = np.matrix(np.vstack([x, np.ones(len(x))]).T)
        beta = np.linalg.inv(X.T * X) * X.T * np.matrix(y).T
        s2 = np.sum((y - (X * beta).A.ravel())**2) / (len(y) - len(beta))
        olscov = np.linalg.inv(X.T * X) * s2

        #now do the non-linear least squares fit
        mod = models.Linear1D(a, b)
        fitter = fitting.LevMarLSQFitter()

        fmod = fitter(mod, x, y)

        assert_allclose(fmod.parameters, beta.A.ravel())
        assert_allclose(olscov, fitter.fit_info['param_cov'])
