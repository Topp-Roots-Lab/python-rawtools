'''
Created on Feb 25, 2020

@author: njiang, tparker
'''

import argparse
import logging
import os
from importlib.metadata import version
from multiprocessing import cpu_count

import imageio.v3 as iio
import numpy as np
from rich.progress import track

from rawtools import log

__version__ = version("rawtools")

def pcd2img(path, format='png', **kwargs):

    for fname in [out for out in os.listdir(path) if out.endswith(".out")]:
        output_dir = os.path.join(path, os.path.splitext(os.path.basename(fname))[0]);
        logging.debug(f"{output_dir=}")
        bname = os.path.basename(output_dir)
        
        indices = np.genfromtxt(os.path.join(path, fname), delimiter = ' ', skip_header = 2)
        width, height, depth = np.amax(indices, axis = 0)
        logging.debug(f"{width=}, {height=}, {depth=}")
        logging.debug(f"{indices=}")

        # Create an empty volume
        volume = np.zeros((int(width+1), int(height+1), int(depth+1)), dtype = np.uint8)
        a = np.rint(indices).astype(np.int32)
        # Flip the vertical orientation
        a[:, 2] = depth - a[:, 2]
        volume[a[:, 0], a[:, 1], a[:, 2]] = 255

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        if 'dryrun' not in kwargs or not kwargs['dryrun']:
            progress_desc = f"Writing slices for '{bname}'"
            for idx in track(range(int(depth+1)), description=progress_desc):
                img = volume[:,:,idx].astype(np.uint8)
                iio.imwrite(output_dir+(f'/{bname}_%04d.{format}'%idx), img, format=format)


def cli():
    description = 'Generate binary slices from .out point cloud'
    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-V", "--version", action="version",
                        version=f'%(prog)s {__version__}')
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Increase output verbosity")
    parser.add_argument("-t", "--threads", type=int, default=cpu_count(),
                        help=f"Maximum number of threads dedicated to processing.")
    parser.add_argument("-n", '--dry-run', dest='dryrun', action="store_true",
                        help="Perform a trial run. Do not create image files, but logs will be updated.")
    parser.add_argument("--format", dest="fileformat",
                        default="png", choices=["png", "tiff"])
    parser.add_argument("path", metavar='PATH', type=str,
                        nargs='+', help='directory of .out files')
    args = parser.parse_args()

    return args


def main():
    args = cli()
    args.module_name = "pcd2img"
    log.configure(args)
    verbose = args.verbose
    threads = args.threads
    path = args.path
    dryrun = args.dryrun
    format = args.fileformat

    for fpath in path:
        logging.debug(f"{args=}")
        pcd2img(fpath, format=format, verbose=verbose,
                threads=threads, dryrun=dryrun)


if __name__ == "__main__":
    main()
