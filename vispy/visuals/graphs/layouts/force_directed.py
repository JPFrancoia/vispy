# -*- coding: utf-8 -*-
# Copyright (c) 2015, Vispy Development Team.
# Distributed under the (new) BSD License. See LICENSE.txt for more info.
"""
Force-Directed Graph Layout
===========================

This module contains implementations for a force-directed layout, where each
edge is modelled like a spring, and the whole graph tries to reach a state
which requires the minimum energy.
"""

import numpy as np

try:
    from scipy.sparse import issparse
except ImportError:
    def issparse(*args, **kwargs):
        return False

from ..util import _straight_line_vertices, rescale_layout


class fruchterman_reingold(object):
    """
    Fruchterman-Reingold implementation adapted from NetworkX.

    Paramters
    ---------
    optimal : number
        Optimal distance between nodes. Defaults to :math:`1/\sqrt{N}` where
        N is the number of nodes.
    iterations : int
        Number of iterations to perform for layout calculation.
    pos : array
        Initial positions of the nodes
    """

    def __init__(self, optimal=None, iterations=50, pos=None):
        self.dim = 2
        self.optimal = optimal
        self.iterations = iterations
        self.num_nodes = None
        self.pos = pos

    def __call__(self, adjacency_mat, directed=False):
        """
        Starts the calculation of the graph layout.

        This is a generator, and after each iteration it yields the new
        positions for the nodes, together with the vertices for the edges
        and the arrows.

        There are two solvers here: one specially adapted for SciPy sparse
        matrices, and the other for larger networks.

        Parameters
        ----------
        adjacency_mat : array
            The graph adjacency matrix.
        directed : bool
            Wether the graph is directed or not. If this is True,
            it will draw arrows for directed edges.

        Yields
        ------
        layout : tuple
            For each iteration of the layout calculation it yields a tuple
            containing (node_vertices, line_vertices, arrow_vertices). These
            vertices can be passed to the `MarkersVisual` and `ArrowVisual`.
        """
        if adjacency_mat.shape[0] != adjacency_mat.shape[1]:
            raise ValueError("Adjacency matrix should be square.")

        self.num_nodes = adjacency_mat.shape[0]

        if issparse(adjacency_mat):
            # Use the sparse solver
            solver = self._sparse_fruchterman_reingold
        else:
            solver = self._fruchterman_reingold

        for result in solver(adjacency_mat, directed):
            yield result

    def _fruchterman_reingold(self, adjacency_mat, directed=False):
        if self.optimal is None:
            self.optimal = 1 / np.sqrt(self.num_nodes)

        if self.pos is None:
            # Random initial positions
            pos = np.asarray(
                np.random.random((self.num_nodes, self.dim)),
                dtype='f32'
            )
        else:
            pos = self.pos.astype('f32')

        # Yield initial positions
        line_vertices, arrows = _straight_line_vertices(adjacency_mat, pos,
                                                        directed)
        yield pos, line_vertices, arrows

        # The initial "temperature"  is about .1 of domain area (=1x1)
        # this is the largest step allowed in the dynamics.
        t = 0.1

        # Simple cooling scheme.
        # Linearly step down by dt on each iteration so last iteration is
        # size dt.
        dt = t / float(self.iterations+1)
        delta = np.zeros(
            (pos.shape[0], pos.shape[0], pos.shape[1]),
            dtype='f32'
        )

        # The inscrutable (but fast) version
        # This is still O(V^2)
        # Could use multilevel methods to speed this up significantly
        for iteration in range(self.iterations):
            delta_pos = self._calculate_delta_pos(adjacency_mat, pos, delta, t)
            pos += delta_pos
            rescale_layout(pos)

            # cool temperature
            t -= dt

            # Calculate edge vertices and arrows
            line_vertices, arrows = _straight_line_vertices(adjacency_mat,
                                                            pos, directed)

            yield pos, line_vertices, arrows

    def _sparse_fruchterman_reingold(self, adjacency_mat, directed=False):
        # Optimal distance between nodes
        if self.optimal is None:
            self.optimal = 1 / np.sqrt(self.num_nodes)

        # Change to list of list format
        # Also construct the matrix in COO format for easy edge construction
        adjacency_mat = adjacency_mat.tocsr()
        adjacency_coo = adjacency_mat.tocoo()

        if self.pos is None:
            # Random initial positions
            pos = np.asarray(
                np.random.random((self.num_nodes, self.dim)),
                dtype='f32'
            )
        else:
            pos = self.pos.astype('f32')

        # Yield initial positions
        line_vertices, arrows = _straight_line_vertices(adjacency_coo, pos,
                                                        directed)
        yield pos, line_vertices, arrows

        # The initial "temperature"  is about .1 of domain area (=1x1)
        # This is the largest step allowed in the dynamics.
        t = 0.1
        # Simple cooling scheme.
        # Linearly step down by dt on each iteration so last iteration is
        # size dt.
        dt = t / float(self.iterations+1)
        delta = np.zeros(
            (pos.shape[0], pos.shape[0], pos.shape[1]),
            dtype='f32'
        )

        for iteration in range(self.iterations):
            delta_pos = self._calculate_delta_pos(adjacency_mat.toarray(), pos,
                                                  delta, t)
            pos += delta_pos
            rescale_layout(pos)

            # Cool temperature
            t -= dt

            # Calculate line vertices
            line_vertices, arrows = _straight_line_vertices(adjacency_coo,
                                                            pos, directed)

            yield pos, line_vertices, arrows

    def _calculate_delta_pos(self, adjacency_mat, pos, delta, t):
        delta[:, :, :] = pos[:, np.newaxis, :] - pos[:, :]

        # Distance between points
        distance = np.sqrt((delta*delta).sum(axis=-1))
        # Enforce minimum distance of 0.01
        distance = np.where(distance < 0.01, 0.01, distance)
        # Displacement "force"
        displacement = (
            delta * (
                (self.optimal * self.optimal) / (distance*distance) -
                (adjacency_mat * distance) / self.optimal
            )[:, :, np.newaxis]
        ).sum(axis=1)

        length = np.sqrt((displacement**2).sum(axis=1))
        length = np.where(length < 0.01, 0.1, length)
        delta_pos = displacement * t / length[:, np.newaxis]

        return delta_pos
