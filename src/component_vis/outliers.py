import numpy as np
import pandas as pd
import scipy.stats as stats

from ._utils import is_iterable
from .factor_tools import construct_cp_tensor
from .xarray_wrapper import is_dataframe, is_xarray

_LEVERAGE_NAME = "Leverage score"
_SLABWISE_SSE_NAME = "Slabwise SSE"


def _compute_leverage(factor_matrix):
    A = factor_matrix
    leverage = A @ np.linalg.solve(A.T @ A, A.T)
    return np.diag(leverage)


def _compute_slabwise_sse(estimated, true, normalise=True, axis=0):
    if not is_iterable(axis):
        axis = {axis}
    axis = set(axis)

    reduction_axis = tuple(i for i in range(true.ndim) if i not in axis)
    SSE = ((estimated - true) ** 2).sum(axis=reduction_axis)
    if normalise:
        return SSE / SSE.sum()
    else:
        return SSE


def compute_slabwise_sse(estimated, true, normalise=True, axis=0):
    r"""Compute the (normalised) slabwise SSE along the given mode(s).

    For a tensor, :math:`\mathcal{X}`, and an estimated tensor :math:`\hat{\mathcal{X}}`,
    we compute the :math:`i`-th normalised slabwise residual as

    .. math::
        r_i = \frac{\sum_{jk} \left(x_{ijk} - \hat{x}_{ijk}\right)^2}
                   {\sum_{ijk} \left(x_{ijk} - \hat{x}_{ijk}\right)^2}.

    The residuals can measure how well our decomposition fits the different
    sample. If a sample, :math:`i`, has a high residual, then that indicates that
    the model is not able to describe its behaviour.

    Parameters
    ----------
    estimated : xarray or numpy array
        Estimated dataset, if this is an xarray, then the output is too.
    true : xarray or numpy array
        True dataset, if this is an xarray, then the output is too.
    normalise : bool
        Whether the SSE should be scaled so the vector sums to one.
    axis : int
        Axis (or axes) that the SSE is computed across (i.e. these are not the ones summed over).
        The output will still have these axes.

    Returns
    -------
    slab_sse : xarray or numpy array
        The (normalised) slabwise SSE, if true tensor input is an xarray array,
        then the returned tensor is too.

    TODO: example for compute_slabwise_sse
    """
    # Check that dimensions match up.
    if is_xarray(estimated) and is_xarray(true):
        if estimated.dims != true.dims:
            raise ValueError(
                f"Dimensions of estimated and true tensor must be equal,"
                f" they are {estimated.dims} and {true.dims}, respectively."
            )
        for dim in estimated.dims:
            if len(true.coords[dim]) != len(estimated.coords[dim]):
                raise ValueError(
                    f"The dimension {dim} has different length for the true and estiamted tensor. "
                    f"The true tensor has length {len(true.coords[dim])} and the estimated tensor "
                    f"has length {len(estimated.coords[dim])}."
                )
            if not all(true.coords[dim] == estimated.coords[dim]):
                raise ValueError(f"The dimension {dim} has different coordinates for the true and estimated tensor.")
    elif is_dataframe(estimated) and is_dataframe(true):
        if estimated.columns != true.columns:
            raise ValueError("Columns of true and estimated matrix must be equal")
        if estimated.index != true.index:
            raise ValueError("Index of true and estimated matrix must be equal")

    slab_sse = _compute_slabwise_sse(estimated, true, normalise=normalise, axis=axis)
    if hasattr(slab_sse, "to_dataframe"):
        slab_sse.name = _SLABWISE_SSE_NAME
    return slab_sse


def compute_leverage(factor_matrix):
    r"""Compute the leverage score of the given factor matrix.

    The leverage score is a measure of how much "influence" a slab (often representing a sample)
    has on a tensor factorisation model. For example, if we have a CP model, :math:`[A, B, C]`,
    where the :math:`A`-matrix represents the samples, then the sample-mode leverage score is
    defined as

    .. math::

        l_i = \left[A \left(A^T A\right)^{-1} A^T\right]_{ii},

    that is, the :math:`i`-th diagonal entry of the matrix :math:`\left[A \left(A^T A\right)^{-1} A^T\right]`.
    If a given sample, :math:`i`, has a high leverage score, then it likely has a strong
    influence on the model.

    # TODO: More description with some mathematical properties (e.g. sums to the rank) and interpretations

    If the factor matrix is a dataframe (i.e. has an index), then the output is
    also a dataframe with that index. Otherwise, the output is a NumPy array.

    Parameters
    ----------
    factor_matrix : DataFrame or numpy array
        The factor matrix whose leverage we compute

    Returns
    -------
    leverage : DataFrame or numpy array
        The leverage scores, if the input is a dataframe, then the index is preserved.
    
    Note
    ----

    The leverage score is related to the Hotelling T2-statistic (or D-statistic), which
    is equal to a scaled version of leverage computed based on centered factor matrices.
    """
    # TODO: example for compute_leverage
    leverage = _compute_leverage(factor_matrix)

    if is_dataframe(factor_matrix):
        return pd.DataFrame(leverage.reshape(-1, 1), columns=[_LEVERAGE_NAME], index=factor_matrix.index)
    else:
        return leverage


def compute_outlier_info(cp_tensor, true_tensor, normalise_sse=True, axis=0):
    f"""Compute the leverage score and (normalised) slabwise SSE along one axis.

    # TODO: Write description of how to use compute_outlier_info.

    These metrics are often plotted against each other to discover outliers.

    Parameters
    ----------
    cp_tensor : CPTensor or tuple
        TensorLy-style CPTensor object or tuple with weights as first
        argument and a tuple of components as second argument
    true_tensor : xarray or numpy array
        Dataset that cp_tensor is fitted against.
    normalise_sse : bool
        If true, the slabwise SSE is scaled so it sums to one.
    axis : int

    Returns
    -------
    DataFrame
        Dataframe with two columns, "{_LEVERAGE_NAME}" and "{_SLABWISE_SSE_NAME}".
    """
    # Add whether suspicious based on rule-of-thumb cutoffs as boolean columns
    leverage = compute_leverage(cp_tensor[1][axis])

    estimated_tensor = construct_cp_tensor(cp_tensor)
    slab_sse = compute_slabwise_sse(estimated_tensor, true_tensor, normalise=normalise_sse, axis=axis)
    if is_xarray(slab_sse):
        slab_sse = pd.DataFrame(slab_sse.to_series())

    leverage_is_labelled = is_dataframe(leverage)
    sse_is_labelled = is_dataframe(slab_sse)
    if (leverage_is_labelled and not sse_is_labelled) or (not leverage_is_labelled and sse_is_labelled):
        raise ValueError(
            "If `cp_tensor` is labelled (factor matrices are dataframes), then"
            "`true_tensor` should be an xarray object and vice versa."
        )
    elif not leverage_is_labelled and not sse_is_labelled:
        return pd.DataFrame({_LEVERAGE_NAME: leverage, _SLABWISE_SSE_NAME: slab_sse})
    elif leverage_is_labelled and not all(slab_sse.index == leverage.index):
        raise ValueError("The indices of the labelled factor matrices does not match up with the xarray dataset")

    results = pd.concat([leverage, slab_sse], axis=1)
    results.columns = [_LEVERAGE_NAME, _SLABWISE_SSE_NAME]
    return results


def get_leverage_outlier_threshold(leverage_scores, method="p_value", p_value=0.05):
    """Compute threshold for detecting possible outliers based on leverage.

    **Huber's heuristic for selecting outliers**

    In Robust Statistics, Huber :cite:p:`huber2009robust` shows that that if the leverage score,
    :math:`h_i`, of a sample is equal to :math:`1/r` and we duplicate that sample, then its leverage
    score will be equal to :math:`1/(1+r)`. We can therefore, think of of the reciprocal of the
    leverage score, :math:`1/h_i`, as the number of similar samples in the dataset. Following this
    logic, Huber recommends two thresholds for selecting outliers: 0.2 (which we name ``"huber low"``)
    and 0.5 (which we name ``"huber high"``).

    **Hoaglin and Welch's heuristic for selecting outliers**

    In :cite:p:`belsley1980regression` (page 17), :cite:authors:`belsley1980regression`, show that if
    the factor matrix is normally distributed, then we can scale leverage, we obtain a Fisher-distributed
    random variable. Specifically, we have that :math:`(n - r)[h_i - (1/n)]/[(1 - h_i)(r - 1)]` follows
    a Fisher distribution with :math:`(r-1)` and :math:`(n-r)` degrees of freedom. While the factor matrix
    seldomly follows a normal distribution, :cite:authors:`belsley1980regression` still argues that this
    can be a good starting point for cut-off values of suspicious data points. They therefore say that
    :math:`2r/n` is a good cutoff in general and that :math:`3r/n` is a good cutoff when :math:`r < 6`
    and :math:`n-r > 12`.

    **Leverage p-value**

    Another way to select ouliers is also based on the findings by :cite:authors:`belsley1980regression`.
    We can use the transformation into a Fisher distributed variable (assuming that the factor elements
    are drawn from a normal distribution), to compute cut-off values based on a p-value. The elements of
    the factor matrices are seldomly normally distributed, so this is also just a rule-of-thumb.

    .. note::
        
        Note also that we, with bootstrap estimation, have found that this p-value is only valid for
        large number of components. For smaller number of components, the false positive rate will be higher
        than the specified p-value, even if the components follow a standard normal distribution (see example below).
    
    **Hotelling's T2 statistic**

    Yet another way to estimate a p-value is via Hotelling's T-squared statistic :cite:p:`nomikos1995multivariate`.
    The key here is to notice that if the factor matrices are normally distributed with zero mean, then
    the leverage is equivalent to a scaled version of the Hotelling's T-squared statistic. This is commonly
    used in PCA, where the data often is centered beforehand, which leads to components with zero mean (in the
    mode the data is centered across). Again, note that the elements of the factor matrices are seldomly normally
    distributed, so this is also just a rule-of-thumb.

    .. note::

        Note also that we, with bootstrap estimation, have found that this p-value is not valid for
        large numbers of components. In that case, the false positive rate will be higher than the specified
        p-value, even if the components follow a standard normal distribution (see example below).

    Parameters
    ----------
    leverage_scores : np.ndarray or pd.DataFrame
    method : {"huber lower", "huber higher", "hw lower", "hw higher", "p-value", "hotelling"}
    p_value : float (optional, default=0.05)
        If ``method="p-value"``, then this is the p-value used for the cut-off.

    Returns
    -------
    threshold : float
        Threshold value, data points with a leverage score larger than the threshold are suspicious
        and may be outliers.

    Examples
    --------

    **The leverage p-value is only accurate with many components:**
    Here, we use Monte-Carlo estimation to demonstrate that the p-value derived in :cite:p:`belsley1980regression`
    is valid only for large number of components.

    We start by importing some utilities

    >>> import numpy as np
    >>> from scipy.stats import bootstrap
    >>> from component_vis.outliers import compute_leverage, get_leverage_outlier_threshold

    Here, we create a function that computes the false positive rate

    >>> def compute_false_positive_rate(n, d, p_value):
    ...     X = np.random.standard_normal((n, d))
    ...
    ...     h = compute_leverage(X)
    ...     th = get_leverage_outlier_threshold(h, method="p-value", p_value=p_value)
    ...     return (h > th).mean()

    >>> np.random.seed(0)
    >>> n_samples = 1_000
    >>> leverages = [compute_false_positive_rate(10, 2, 0.05) for _ in range(n_samples)],
    >>> fpr_low, fpr_high = bootstrap(leverages, np.mean).confidence_interval
    >>> print(f"95% confidence interval for the false positive rate: [{fpr_low:.4f}, {fpr_high:.4f}]")
    95% confidence interval for the false positive rate: [0.0815, 0.0897]

    We see that the false positive rate is almost twice what we prescribe (0.05). However, if we increase
    the number of components, then the false positive rate improves

    >>> leverages = [compute_false_positive_rate(10, 9, 0.05) for _ in range(n_samples)],
    >>> fpr_low, fpr_high = bootstrap(leverages, np.mean).confidence_interval
    >>> print(f"95% confidence interval for the false positive rate: [{fpr_low:.4f}, {fpr_high:.4f}]")
    95% confidence interval for the false positive rate: [0.0468, 0.0554]

    This indicates that the false positive rate is most accurate when the number of components is equal
    to the number of samples - 1. We can increase the number of samples to assess this conjecture

    >>> leverages = [compute_false_positive_rate(100, 9, 0.05) for _ in range(n_samples)],
    >>> fpr_low, fpr_high = bootstrap(leverages, np.mean).confidence_interval
    >>> print(f"95% confidence interval for the false positive rate: [{fpr_low:.4f}, {fpr_high:.4f}]")
    95% confidence interval for the false positive rate: [0.0558, 0.0581]

    The increase in the false positive rate supports the conjecture that :cite:author:`belsley1980regression`'s
    method for computing the p-value is accurate only when the number of components is high. Still, it is
    important to remember that the original assumptions (normally distributed components) is seldomly satisfied
    also, so this method is only a rule-of-thumb and can still be useful.

    **Hotelling's T-squared statistic requires few components or many samples:**
    Here, we use Monte-Carlo estimation to demonstrate that the Hotelling T-squared statistic is only valid with
    many samples.

    >>> def compute_hotelling_false_positive_rate(n, d, p_value):
    ...     X = np.random.standard_normal((n, d))
    ...
    ...     h = compute_leverage(X)
    ...     th = get_leverage_outlier_threshold(h, method="hotelling", p_value=p_value)
    ...     return (h > th).mean()

    We set the simulation parameters and the seed

    >>> np.random.seed(0)
    >>> n_samples = 1_000
    >>> fprs = [compute_hotelling_false_positive_rate(10, 2, 0.05) for _ in range(n_samples)],
    >>> fpr_low, fpr_high = bootstrap(fprs, np.mean).confidence_interval
    >>> print(f"95% confidence interval for the false positive rate: [{fpr_low:.4f}, {fpr_high:.4f}]")
    95% confidence interval for the false positive rate: [0.0492, 0.0568]

    However, if we increase the number of components, then the false positive rate becomes to large

    >>> fprs = [compute_hotelling_false_positive_rate(10, 5, 0.05) for _ in range(n_samples)],
    >>> fpr_low, fpr_high = bootstrap(fprs, np.mean).confidence_interval
    >>> print(f"95% confidence interval for the false positive rate: [{fpr_low:.4f}, {fpr_high:.4f}]")
    95% confidence interval for the false positive rate: [0.0746, 0.0842]

    But if we increase the number of samples, then the estimate is good again

    >>> fprs = [compute_hotelling_false_positive_rate(100, 5, 0.05) for _ in range(n_samples)],
    >>> fpr_low, fpr_high = bootstrap(fprs, np.mean).confidence_interval
    >>> print(f"95% confidence interval for the false positive rate: [{fpr_low:.4f}, {fpr_high:.4f}]")
    95% confidence interval for the false positive rate: [0.0494, 0.0515]
    """
    num_samples = len(leverage_scores)
    num_components = np.sum(leverage_scores)

    method = method.lower()
    if method == "huber lower":
        return 0.2
    elif method == "huber higher":
        return 0.5
    elif method == "hw lower":
        return 2 * num_components / num_samples
    elif method == "hw higher":
        return 3 * num_components / num_samples
    elif method == "p-value":
        n, p = num_samples, num_components

        if p <= 1:
            raise ValueError("Cannot use P-value when there is only one component.")
        if n <= p:
            raise ValueError("Cannot use P-value when there are fewer samples than components.")

        F = stats.f.isf(p_value, p - 1, n - p)
        F_scale = F * (p - 1) / (n - p)
        # Solve the equation (h + (1/n)) / (1 - h) = F_scale:
        return (F_scale + (1 / n)) / (1 + F_scale)
    elif method == "hotelling":
        I, R = num_samples, num_components
        F = stats.f.isf(p_value, R, I - R - 1)
        B = (R / (I - R - 1)) * F / (1 + (R / (I - R - 1)) * F)
        return (
            B * (I - 1) / I
        )  # Remove the square compared to Nomikos & MacGregor since the leverage is A(AtA)^-1 At, not A(AtA / (I-1))^-1 At
    else:
        raise ValueError(
            "Method must be one of 'huber lower', 'huber higher', 'hw lower' or 'hw higher', "
            + f"'p-value', or 'hotelling' not {method}"
        )


def get_slab_sse_outlier_threshold(slab_sse, method="p_value", p_value=0.05, ddof=1):
    r"""Compute rule-of-thumb threshold values for suspicious residuals.

    One way to determine possible outliers is to examine how well the model describes
    the different data points. A standard way of measuring this, is by the slab-wise
    sum of squared errors (slabwise SSE), which is the sum of squared error for each
    data point.

    There is, unfortunately, no guaranteed way to detect outliers automatically based
    on the residuals. However, if the noise is normally distributed, then the residuals
    follow a scaled chi-squared distribution. Specifically, we have that
    :math:`\text{SSE}_i^2 \sim g\chi^2_h`, where :math:`g = \frac{\sigma^2}{2\mu}`,
    :math:`h = \frac{\mu}{g} = \frac{2\mu^2}{\sigma^2}`, and :math:`\mu` is the
    average slabwise SSE and :math:`\sigma^2` is the variance of the slabwise
    SSE :cite:p:`nomikos1995multivariate`.

    Another rule-of-thumb follows from :cite:p:`naes2002user` (p. 187), which states
    that two times the standard deviation of the slabwise SSE can be used for
    determining data points with a suspiciously high residual.

    Parameters
    ----------
    slab_sse : np.ndarray or pd.DataFrame
    method : {"two_sigma", "p_value"}
    p_value : float (optional, default=0.05)
        If ``method="p-value"``, then this is the p-value used for the cut-off.

    Returns
    -------
    threshold : float
        Threshold value, data points with a higher SSE than the threshold are suspicious
        and may be outliers.
    """
    # TODO: documentation example for get_slab_sse_outlier_threshold
    std = np.std(slab_sse, ddof=ddof)
    mean = np.mean(slab_sse)
    if method == "two sigma":
        return std * 2
    elif method == "p-value":
        g = std * std / (2 * mean)
        h = mean / g
        return stats.chi2.isf(p_value, h) * g
    else:
        raise ValueError(f"Method must be one of 'two sigma' and 'p-value', not '{method}'.")

