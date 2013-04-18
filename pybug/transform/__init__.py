import numpy as np
import hashlib
from matplotlib import pyplot


class AlignmentError(Exception):
    pass


class Transformation(object):
    """
    An abstract representation of any n-dimensional transformation.
    Provides a unified interface to apply the transformation (:meth:`apply`)
    """

    def apply(self, x):
        """

        :param x:
        :raise:
        """
        raise NotImplementedError


class AffineTransformation(Transformation):
    """
    The base class for all n-dimensional affine transformations. Provides
    methods to break the transform down into it's constituent
    scale/rotation/translation, to view the homogeneous matrix equivalent,
    and to chain this transformation with other affine transformations.
    """

    def __init__(self, homogeneous_matrix):
        self.homogeneous_matrix = homogeneous_matrix

    def chain(self, x):
        """
        Chains this affine transformation with another one,
        producing a new affine transformation
        """
        return AffineTransformation(np.dot(self.homogeneous_matrix,
                                           x.homogeneous_matrix))

    def apply(self, x):
        """
        Applies this transformation to a new set of vectors
        """
        return np.dot(self.linear_transformation, x + self.translation)

    @property
    def linear_transformation(self):
        """
        Returns just the linear transformation component of this affine
        transformation.
        """
        return self.homogeneous_matrix[:-1, :-1]

    @property
    def translation(self):
        """
        Returns just the transformation aspect of this affine transformation.
        """
        return self.homogeneous_matrix[-1, :-1]


class Translation(AffineTransformation):
    """
    An n_dim translation transformation.
    """

    def __init__(self, transformation):
        """
        translation : a 1-d ndarray of length n_dim (i.e.
        if you want to make a 3d translation you must specify the
        translation in each dimension explicitly).
        """
        homogeneous_matrix = np.eye(transformation.size + 1)
        homogeneous_matrix[-1, :-1] = transformation
        super(Translation, self).__init__(homogeneous_matrix)


class Rotation(AffineTransformation):
    """
    An n_dim rotation transformation.
    """

    def __init__(self, rotation):
        """ The rotation must be a 2-d square ndarray of shape (n_dim, n_dim)
        By default
        """
        homogeneous_matrix = np.eye(rotation.shape[0] + 1)
        homogeneous_matrix[:-1, :-1] = rotation
        super(Rotation, self).__init__(homogeneous_matrix)


class Alignment(object):
    """ Aligns a single source object to a target.
    """

    def __init__(self, source, target):
        """ source - ndarray of landmarks which will be aligned of dimension
         [n_landmarks x n_dim]

        target  - an ndarray (of the same dimension of source) which
                  the source will be aligned to.
        """
        self.source = source
        self.aligned_source = self.source.copy()
        try:
            self.n_landmarks, self.n_dim = self.source.shape
        except ValueError:
            raise AlignmentError('Data is being provided in an invalid format'
                                 ' - must have shape (n_landmarks, n_dim)')
        assert self.n_dim, self.n_landmarks == target.shape
        self.target = target

    def _view_2d(self):
        """ Visualize how points are affected by the warp in 2 dimensions.
    """
        # a factor by which the minimum and maximum x and y values of the warp
        # will be increased by.
        x_margin_factor, y_margin_factor = 0.5, 0.5
        # the number of x and y samples to take
        n_x, n_y = 50, 50
        # {x y}_{min max} is the actual bounds on either source or target
        # landmarks
        x_min, y_min = np.vstack(
            [self.target.min(0), self.source.min(0)]).min(0)
        x_max, y_max = np.vstack(
            [self.target.max(0), self.source.max(0)]).max(0)
        x_margin = x_margin_factor * (x_max - x_min)
        y_margin = y_margin_factor * (y_max - y_min)
        # {x y}_{min max}_m is the bound once it has been grown by the factor
        # of the spread in that dimension
        x_min_m = x_min - x_margin
        x_max_m = x_max + x_margin
        y_min_m = y_min - y_margin
        y_max_m = y_max + y_margin
        # build sample points for the selected region
        x = np.linspace(x_min_m, x_max_m, n_x)
        y = np.linspace(y_min_m, y_max_m, n_y)
        xx, yy = np.meshgrid(x, y)
        sample_coords = np.concatenate(
            [xx.reshape([-1, 1]), yy.reshape([-1, 1])], axis=1)
        warped_coords = self.mapping(sample_coords)
        delta = warped_coords - sample_coords
        # plot the sample points result
        pyplot.quiver(sample_coords[:, 0], sample_coords[:, 1], delta[:, 0],
                      delta[:, 1])
        delta = self.target - self.source
        # plot how the landmarks move from src to target
        pyplot.quiver(self.source[:, 0], self.source[:, 1], delta[:, 0],
                      delta[:, 1])
        # rescale to the bounds
        pyplot.xlim((x_min_m, x_max_m))
        pyplot.ylim((y_min_m, y_max_m))


class ParallelAlignment(object):
    def __init__(self, sources, target=None):
        """ sources - an iterable of numpy arrays of landmarks which will be
                    aligned e.g. [landmarks_0, landmarks_1,
                    ...landmarks_n] where landmarks is an ndarray of
                    dimension [n_landmarks x n_dim]
          KWARGS
            target  - a single numpy array (of the same dimension of sources)
                    which every instance of source will be aligned to. If
                    not present, target is set to the mean source position.
        """
        self._lookup = {}
        if type(sources) == np.ndarray:
            # only a single landmark passed in
            sources = [sources]
        n_sources = len(sources)
        n_landmarks = sources[0].shape[0]
        n_dim = sources[0].shape[1]
        self.sources = np.zeros([n_landmarks, n_dim, n_sources])
        for i, source in enumerate(sources):
            assert n_dim, n_landmarks == source.shape
            self.sources[:, :, i] = source
            source_hash = _numpy_hash(source)
            self._lookup[source_hash] = i
        self.aligned_sources = self.sources.copy()
        if target is None:
            # set the target to the mean source position
            self.target = self.sources.mean(2)[..., np.newaxis]
        else:
            assert n_dim, n_landmarks == target.shape
            self.target = target[..., np.newaxis]

    @property
    def n_landmarks(self):
        return self.sources.shape[0]

    @property
    def n_dimensions(self):
        return self.sources.shape[1]

    def aligned_version_of_source(self, source):
        i = self._lookup[_numpy_hash(source)]
        return self.aligned_sources[..., i]

    @property
    def n_sources(self):
        return self.sources.shape[2]


def _numpy_hash(array):
    """ Efficiently generates a hash of a numpy array.
  """
    # view the array as chars, then hash it.
    return hashlib.sha1(array.view(np.uint8)).hexdigest()
