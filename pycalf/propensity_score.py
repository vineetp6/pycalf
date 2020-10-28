import copy
import numpy as np
import pandas as pd

from sklearn.neighbors import NearestNeighbors


class Matching():
    def __init__(self, learner, eps=1e-2):
        self.learner = learner
        self.p_score = None
        self.eps = 1e-2

    def fit(self, X, treatment, y, clip=1e-15):
        self.learner.fit(X, treatment)
        assert 0 <= clip < 1, 'clip must be 0 to 1.'
        self.p_score = np.clip(self.learner.predict_proba(X)[:, 1], clip, 1 - clip)

    def get_score(self):
        return self.p_score

    def get_weight(self, treatment, mode='ate'):
        self._check_mode(mode)
        if mode == 'raw':
            return np.ones(treatment.shape[0])
        elif mode == 'ate':
            return self._get_matche_weight(treatment, self.p_score)

    def _check_mode(self, mode):
        mode_list = ['raw', 'ate', 'att', 'atu']
        assert mode in mode_list, 'mode must be string and it is raw, ate, att or atu.'

    def _get_matche_weight(self, treatment, score):
        neigh = NearestNeighbors(n_neighbors=5, metric='manhattan')
        neigh.fit(score[~treatment].reshape(-1, 1))
        neigh_dist, neigh_idx = neigh.kneighbors(
            score[treatment].reshape(-1, 1), 1, return_distance=True)
        neigh_idx = neigh_idx[neigh_dist < self.eps]

        treat_idx = np.where(treatment)[0]
        control_idx = np.where(~treatment)[0]
        treat_idx = treat_idx
        control_idx = control_idx[neigh_idx.flatten()]

        smpl_idx = np.concatenate((control_idx, treat_idx), axis=0)
        idx, counts = np.unique(smpl_idx, return_counts=True)
        weights = np.zeros(treatment.shape[0])
        for i, c in zip(idx, counts):
            weights[i] = c
        return weights

    def estimate_effect(self, treatment, y, mode='ate'):
        self._check_mode(mode)
        weight = self.get_weight(treatment, mode=mode)
        return self._estimate_outcomes(treatment, y, weight)

    def _estimate_outcomes(self, treatment, y, weight):
        avg_y_control = np.average(y[~treatment], axis=0, weights=weight[~treatment])
        avg_y_treat = np.average(y[treatment], axis=0, weights=weight[treatment])
        effect_size = avg_y_treat - avg_y_control
        return (avg_y_control, avg_y_treat, effect_size)


class IPW():
    """Inverse Probability Weighting Method.
    """

    def __init__(self, learner):
        self.learner = learner
        self.p_score = None

    def fit(self, X, treatment, clip=1e-15):
        """Fit Leaner and Calculation IPW.

        Parameters
        ----------
        X : numpy ndarray, DataFrame

        treatment : numpy ndarray, Series

        clip : float

        Returns
        -------
        None
        """
        self.learner.fit(X, treatment)
        assert 0 <= clip < 1, 'clip must be 0 to 1.'
        self.p_score = np.clip(self.learner.predict_proba(X)[:, 1], clip, 1 - clip)

    def get_score(self):
        return self.p_score

    def get_weight(self, treatment, mode='ate'):
        self._check_mode(mode)
        if mode == 'raw':
            return np.ones(treatment.shape[0])
        elif mode == 'ate':
            return np.where(treatment == 1, 1 / self.p_score, 1 / (1 - self.p_score))
        elif mode == 'att':
            return np.where(treatment == 1, 1, self.p_score / (1 - self.p_score))
        elif mode == 'atu':
            return np.where(treatment == 1, (1 - self.p_score) / self.p_score, 1)

    def estimate_effect(self, treatment, y, mode='ate'):
        """Description

        Parameters
        ----------
        treatment : np.ndarray, pd.Series

        outcomes : pd.DataFrame

        Returns
        -------
        pd.DataFrame
        """
        self._check_mode(mode)
        weight = self.get_weight(treatment, mode=mode)
        return self._estimate_outcomes(treatment, y, weight)

    def _check_mode(self, mode):
        mode_list = ['raw', 'ate', 'att', 'atu']
        assert mode in mode_list, 'mode must be string and it is raw, ate, att or atu.'

    def _estimate_outcomes(self, treatment, y, weight):
        """Description

        Parameters
        ----------
        treatment : np.ndarray

        y :  np.ndarray

        weight : np.ndarray

        Returns
        -------
        (y_control, y_treat, effect_size) : tuple
        """
        avg_y_control = np.average(y[~treatment], axis=0, weights=weight[~treatment])
        avg_y_treat = np.average(y[treatment], axis=0, weights=weight[treatment])
        effect_size = avg_y_treat - avg_y_control
        return (avg_y_control, avg_y_treat, effect_size)


class DoubleRobust(IPW):
    def __init__(self, learner, second_learner):
        super(DoubleRobust, self).__init__(learner)
        self.treat_learner = copy.deepcopy(second_learner)
        self.control_learner = copy.deepcopy(second_learner)

    def estimate_effect(self, X, treatment, y, mode='ate'):
        self._check_mode(mode)
        weight = self.get_weight(treatment, mode=mode)
        return self._estimate_outcomes(X, treatment, y, weight)

    def _estimate_outcomes(self, X, treatment, y, weight):
        y_control = np.zeros(y.shape)
        y_treat = np.zeros(y.shape)
        # Fit second models
        for i, _y in enumerate(y.T):
            self.treat_learner.fit(X[treatment], _y[treatment])
            self.control_learner.fit(X[~treatment], _y[~treatment])

            y_control[:, i] = np.where(
                ~treatment, _y, self.control_learner.predict(X)
            )
            y_treat[:, i] = np.where(
                treatment, _y, self.treat_learner.predict(X)
            )

        avg_y_control = np.average(y_control, axis=0, weights=weight)
        avg_y_treat = np.average(y_treat, axis=0, weights=weight)
        effect_size = avg_y_treat - avg_y_control
        return (avg_y_control, avg_y_treat, effect_size)
