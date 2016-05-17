import re
from numpy import *
from matplotlib import pyplot as plt
from scipy import interpolate
from mpltools import color
import numpy as np

def find_nearest(array,value):
    idx = (abs(array-value)).argmin()
    return idx

def load_fld(df, do_plot=True, do_log=True, xlim=None, ylim=None, clim=None, figsize=(6.,12.),
             plot_axes='xy', cmap=plt.cm.Spectral):
    """
    Load .fld files from Maxwell.
    :param df: Path of the Maxwell data file (fld)
    :param do_plot: Use pcolormesh to plot the 3D data
    :param do_log: Plot the log10 of the array. Note that clim has to be adjusted accordingly
    :param xlim: Dafaults to None. May be any tuple.
    :param ylim: Defaults to None, May be any tuple.
    :param clim: Defaults to None, May be any tuple.
    :param figsize: Tuple of two floats, indicating the figure size for the plot (only if do_plot=True)
    :param plot_axes: May be any of the following: 'xy' (Default), 'xz' or 'yz'
    :return:
    """

    data = loadtxt(df, skiprows=2)
    x = data[:,0]
    y = data[:,1]
    z = data[:,2]
    magE = data[:,3]

    # Determine the shape of the array:
    if 'x' in plot_axes:
        for idx, X in enumerate(x):
            if X != x[0]:
                ysize=idx
                xsize=shape(magE)[0]/ysize
                break
    else:
        for idx, Y in enumerate(y):
            if Y != y[0]:
                ysize=idx
                xsize=shape(magE)[0]/ysize
                break

    # Cast the voltage data in an array:
    if plot_axes == 'xy':
        X = x.reshape((xsize, ysize))
        Y = y.reshape((xsize, ysize))
    if plot_axes == 'xz':
        X = x.reshape((xsize, ysize))
        Y = z.reshape((xsize, ysize))
    if plot_axes == 'yz':
        X = y.reshape((xsize, ysize))
        Y = z.reshape((xsize, ysize))

    E = magE.reshape((xsize, ysize))

    if do_plot:
        plt.figure(figsize=figsize)
        if do_log:
            plt.pcolormesh(X*1E6, Y*1E6, log10(E), cmap=cmap)
        else:
            plt.pcolormesh(X*1E6, Y*1E6, E, cmap=cmap)

        plt.colorbar()

        if clim is not None:
            plt.clim(clim)
        if xlim is None:
            plt.xlim([np.min(X)*1E6, np.max(X)*1E6]);
        else:
            plt.xlim(xlim)
        if ylim is None:
            plt.ylim([np.min(Y)*1E6, np.max(Y)*1E6]);
        else:
            plt.ylim(ylim)
        plt.xlabel('x ($\mu\mathrm{m}$)')
        plt.ylabel('y ($\mu\mathrm{m}$)')

    return X, Y, E

def get_maxwell_boundary_data(df):
    """
    Loads a .dsp file from Maxwell and extracts elements, nodes and the solution at the nodes.
    :param df: File path of the data file
    :return: elements, node, element solution
    """
    with open(df, 'r') as myfile:
        data = myfile.readlines()

    # The important data is stored on line numbers 91-93.
    # Line 91: Elements: Each element is composed of 6 nodes. Each sequence of 2,3,3,0,6 is followed by 6 points, which will
    # make up a single element. First 2 entries are diagnostic info.
    # Line 92: Node coordinates. One node coordinate has 3 entries: x, y, z
    # Line 93: Solution on each node. First 3 entries are diagnostic info.

    line_nr = [91, 92, 93]
    elements = array(re.findall(r"\((.*?)\)", data[line_nr[0]-1])[0].split(', '), dtype=int)
    nodes = array(re.findall(r"\((.*?)\)", data[line_nr[1]-1])[0].split(', '), dtype=float)
    elem_solution = array(re.findall(r"\((.*?)\)", data[line_nr[2]-1])[0].split(', '), dtype=float)

    nodes = nodes.reshape((nodes.shape[0]/3, 3))

    return elements, nodes, elem_solution[3:]

def prepare_for_interpolation(elements, nodes, elem_solution):
    """
    Prepare for files for interpolation of the boundary conditions. We need to do this to cast the boundary conditions
    obtained from get_maxwell_boundary_data to the BEM mesh. These nodes of these meshes don't coincide, so we
    interpolate the boundary conditions on the FEM mesh for each point in the BEM mesh.
    :param elements: elements from get_maxwell_boundary
    :param nodes: nodes from get_maxwell_boundary
    :param elem_solution: elem_solution from get_maxwell_boundary
    :return: x (unique FEM node point x-coordinates), y (unique FEM node point y-coordinates), BC (unique FEM node point solution)
    """
    # Detect what the orientation of this plane is:
    constant_coordinate = [len(unique(diff(nodes[:,k])))==1 for k in range(3)]

    # Select the non-constant coordinates:
    plot_coords = arange(0,3)[logical_not(constant_coordinate)]
    axes_labels = array(['x', 'y', 'z'])[logical_not(constant_coordinate)]

    # Filter out the repeating sequence 2, 3, 3, 0, 6 !! CAREFUL !! may be source of error
    structured_elements = delete(elements, concatenate((where(elements==0)[0], where(elements==0)[0]-3, where(elements==0)[0]-2,
                                                        where(elements==0)[0]-1, where(elements==0)[0]+1)))[2:]
    # Each element consists of 6 points
    structured_elements = structured_elements.reshape((structured_elements.shape[0]/6, 6))
    x = nodes[structured_elements-1,plot_coords[0]]
    y = nodes[structured_elements-1,plot_coords[1]]

    # Remove double points for the interpolation
    unique_points,  unique_indices = unique((x + 1j*y).flatten(), return_index=True)

    x_unique = x.flatten()[unique_indices]
    y_unique = y.flatten()[unique_indices]
    U_unique = elem_solution.flatten()[unique_indices]

    return x_unique, y_unique, U_unique

def interpolate_BC(xdata, ydata, Udata, xeval, yeval, method='cubic'):
    """
    Interpolate a single point on the boundary BEM mesh at (xeval, yeval).
    :param xdata: x-coordinates of the unique FEM nodes (from prepare_for_interpolation)
    :param ydata: y-coordinates of the unique FEM nodes
    :param Udata: Solution at the unique FEM nodes
    :param xeval: x-coordinate for interpolation
    :param yeval: y-coordinate for interpolation
    :return: the interpolated value. If (xeval, yeval) outside the domain of xdata, ydata then np.nan
    """
    # There are different interpolation methods, and they can be compared with the method that
    # Maxwell uses to interpolate the data. In this case, the linear interpolation can be quite decent,
    # but the cubic approximates the Maxwell data better.
    if xeval >= np.min(xdata) and xeval <= np.max(xdata):
        if yeval >= np.min(ydata) and yeval <= np.max(ydata):
            return interpolate.griddata(zip(xdata, ydata), Udata, (xeval, yeval) , method=method)
        else:
            return nan
    else:
        return nan

def plot_BC(xdata, ydata, Udata, xeval=None, yeval=None, cmap=plt.cm.Spectral, clim=None, plot_axes='xy'):
    """
    Compare the FEM data with the interpolated result on the BEM mesh.
    :param xdata: x-coordinates of the unique FEM nodes (from prepare_for_interpolation)
    :param ydata: y-coordinates of the unique FEM nodes
    :param Udata: Solution at the unique FEM nodes
    :param xeval: x-coordinate for interpolation
    :param yeval: y-coordinate for interpolation
    :param cmap: Color map to be used
    :param clim: Tuple, color limits
    :param plot_axes: Default is 'xy'
    :return: BEM Mesh x-points, BEM Mesh y-points, Interpolated BC on BEM mesh
    """
    if xeval is None:
        xeval = linspace(np.min(xdata), np.max(xdata), 501)
    if yeval is None:
        yeval = linspace(np.min(ydata), np.max(ydata), 501)

    X_eval, Y_eval = meshgrid(xeval, yeval)

    plt.figure(figsize=(6.,4.))
    plt.title("Unique nodes")
    plt.plot(xdata, ydata, '.k', alpha=0.5)
    plt.xlabel("{} (mm)".format(plot_axes[0]))
    plt.ylabel("{} (mm)".format(plot_axes[1]))

    # There are different interpolation methods, and they can be compared with the method that
    # Maxwell uses to interpolate the data. In this case, the linear interpolation can be quite decent,
    # but the cubic approximates the Maxwell data better.
    f = interpolate.griddata(zip(xdata, ydata), Udata, (X_eval, Y_eval) , method='cubic')

    plt.figure(figsize=(7.,4.))
    plt.title("Cubic interpolation of solution on unique nodes")
    plt.pcolormesh(X_eval, Y_eval, f, cmap=cmap)
    plt.colorbar()
    if clim is not None:
        plt.clim(clim)
    plt.xlim(min(xeval), max(xeval))
    plt.ylim(min(yeval), max(yeval))
    plt.xlabel("{} (mm)".format(plot_axes[0]))
    plt.ylabel("{} (mm)".format(plot_axes[1]))

    return X_eval, Y_eval, f

def plot_mesh(df):
    """
    Plot the FEM mesh from a .dsp file. Uses get_maxwell_boundary_data. May be slow for large files.
    :param df: File path of the FEM mesh.
    :return: None
    """
    # Load the data file
    elements, nodes, elem_solution = get_maxwell_boundary_data(df)

    # Detect what the orientation of this plane is:
    constant_coordinate = [len(unique(diff(nodes[:,k])))==1 for k in range(3)]

    # Select the non-constant coordinates:
    plot_coords = arange(0,3)[logical_not(constant_coordinate)]
    axes_labels = array(['x', 'y', 'z'])[logical_not(constant_coordinate)]

    # Filter out the repeating sequence 2, 3, 3, 0, 6 !! CAREFUL !! may be source of error
    structured_elements = delete(elements, concatenate((where(elements==0)[0], where(elements==0)[0]-3,
                                                        where(elements==0)[0]-2, where(elements==0)[0]-1,
                                                        where(elements==0)[0]+1)))[2:]
    # Each element consists of 6 points
    structured_elements = structured_elements.reshape((structured_elements.shape[0]/6, 6))

    plt.figure(figsize=(7.,5.))
    plt.title("Mesh elements for {:s}".format(os.path.split(df)[-1]))
    plt.plot(nodes[:,plot_coords[0]], nodes[:,plot_coords[1]], '.k', alpha=0.5)

    color.cycle_cmap(structured_elements.shape[0], cmap=plt.cm.Spectral)

    # Plot the mesh
    x = nodes[structured_elements-1,plot_coords[0]]
    y = nodes[structured_elements-1,plot_coords[1]]

    # Get the center of mass of each element
    xc = mean(x, axis=1)
    yc = mean(y, axis=1)

    for k in range(structured_elements.shape[0]):
        plt.plot([x[k,p] for p in [0,2,5,0]], [y[k,p] for p in [0,2,5,0]])

    plt.xlabel("{} (mm)".format(axes_labels[0]))
    plt.ylabel("{} (mm)".format(axes_labels[1]))
    # Make sure that the prefactors are right in + and - cases.
    plt.xlim(array([0.95, 1.05])[int(np.min(x)<0)]*np.min(x),
             array([0.95, 1.05])[int(np.max(x)>0)]*np.max(x))
    plt.ylim(array([0.95, 1.05])[int(np.min(y)<0)]*np.min(y),
             array([0.95, 1.05])[int(np.max(y)>0)]*np.max(y))

def construct_vertices(xy , uv):
    """
    Preparation method for fast interpolation. This method calculates vertices and weights once, such that
    the interpolation can be done much quicker than e.g. scipy.interpolate.griddata
    :param xy: X,Y coordinates of FEM mesh
    :param uv: X,Y coordinates of the BEM mesh
    :return: Vertices, Weights
    """
    import scipy.spatial.qhull as qhull
    tri = qhull.Delaunay(xy)
    simplex = tri.find_simplex(uv)
    vertices = np.take(tri.simplices, simplex, axis=0)
    temp = np.take(tri.transform, simplex, axis=0)
    delta = uv - temp[:, 2]
    bary = np.einsum('njk,nk->nj', temp[:, :2, :], delta)
    return vertices, np.hstack((bary, 1 - bary.sum(axis=1, keepdims=True)))

def fast_interpolate(values, vertices, weights):
    """
    Fast interpolation method (linear), to be executed after construct_vertices
    :param values: Values of the FEM solution at the FEM mesh points
    :param vertices: from construct_vertices
    :param weights: from construct_vertices
    :return: Interpolated values at the BEM mesh points.
    """
    return np.einsum('nj,nj->n', np.take(values, vertices), weights)