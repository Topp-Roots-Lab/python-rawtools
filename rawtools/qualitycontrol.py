"""
# Quality Control for RAW Volumes

Originally, this tool extracted a slice, the n<sup>th</sup> index from a 16-bit unsigned
integer `.raw` volume. By default, it will extract the midslice, the middle most
slice from the volume from a side view. It has now evolved to also include projections
from a top-view and side-view of a volume.

## Table of Contents

- [Input & Output](#input-&-output)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)

## Input & Output

### Input

The input data consists of a `.raw` and its paired `.dat` file. Both of these
can be generated either by the NorthStar Imaging (NSI) Software from exporting a
`.raw` volume.

### Output

The output consists of 2 types of files.

- 16-bit grayscale, non-interlaced PNG, extracted side-view slice (default: middle most slice)
- 8-bit RGBA, non-interlaced PNG, projection (brightest values across a given axis)

|Example Slice|Example Projection|
|-|-|
|<img src="../../doc/img/midslice_example.png" width="400">|<img src="../../doc/img/side_projection_example.png" width="400">|

## Usage

```txt
usage: qc-raw [-h] [-v] [-V] [-f] [--si] [-p PROJECTION [PROJECTION ...]]
                 [--scale [STEP]] [-s [INDEX]] [--font-size FONT_SIZE]
                 PATHS [PATHS ...]

Check the quality of a .RAW volume by extracting a slice or generating a
projection. Requires a .RAW and .DAT for each volume.

positional arguments:
  PATHS                 Filepath to a .RAW or path to a directory that
                        contains .RAW files.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Increase output verbosity (default: False)
  -V, --version         show program's version number and exit
  -f, --force           Force file creation. Overwrite any existing files.
                        (default: False)
  --si                  Print human readable sizes (e.g., 1 K, 234 M, 2 G)
                        (default: False)
  -p PROJECTION [PROJECTION ...], --projection PROJECTION [PROJECTION ...]
                        Generate projection using maximum values for each
                        slice. Available options: [ 'top', 'side' ]. (default:
                        None)
  --scale [STEP]        Add scale on left side of a side projection. Step is
                        the number of slices between each label. (default:
                        100)
  -s [INDEX], --slice [INDEX]
                        Extract a slice from volume's side view. (default:
                        floor(x/2))
  --font-size FONT_SIZE
                        Font size of labels of scale. (default: 24)
```

### Single project conversion

```bash
qc-raw 2_252.raw -s -p side
```

### Batch conversion

```bash
qc-raw "/media/data" --projection side --slice
```

Example output

```bash
# qc-raw /media/data/ --projection top side
2020-02-22 22:46:36,859 - [INFO] - qc-raw.py 368 - Found 1 .raw file(s).
2020-02-22 22:46:36,859 - [INFO] - qc-raw.py 386 - Processing '/media/data/398-1_CML247_104um.raw' (858640500 B)
Generating side-view projection: 100%|████████████| 999/999 [00:00<00:00, 1543.58it/s]
Generating top-down projection: 100%|█████████████| 999/999 [00:00<00:00, 1649.96it/s]
```

### Adding a scale

The horizontal line stands the number of pixels above it. If the label
is for slice #500, that means there are 500 slices above it. The horizontal line
is the 501<sup>st</sup> slice.

## Troubleshooting

Check the generated log file for a list of debug statements. It appears in the
directory where you ran the script.

Please submit a Git Issue to report errors or make feature requests.
"""
# -*- coding: utf-8 -*-
import logging
import math
import os
import re
import sys
from datetime import datetime as dt

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageMath
from tqdm import tqdm
from rawtools import dat
from pathlib import Path

font = None


def rawfp2datfp(fp):
    directory = os.path.dirname(fp)
    name = os.path.splitext(os.path.basename(fp))[0]
    return os.path.join(directory, f"{name}.dat")


def sizeof_fmt(num, suffix="B", factor=1000.0):
    units = ["", "K", "M", "G", "T", "P", "E", "Z"]
    for unit in units:
        if abs(num) < factor:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= factor
    return "%.1f%s%s" % (num, "Y", suffix)


def get_top_down_projection(args, fp):
    """Generate a projection from the top-down view of a volume, using its maximum values per horizontal slice

    Args:
      args (Namespace): user-defined arguments
      fp (str): filepath for a .RAW volume

    """
    # Extract the resolution from .DAT file
    dat_fp = rawfp2datfp(fp)
    logging.debug(f"{dat_fp=}")
    x, y, z = dat.read(dat_fp)["dimensions"]
    logging.debug(f"Volume dimensions: {x}, {y}, {z}")

    # NOTE(tparker): Patch to skip volumes of unexpected size
    expected_size = x * y * z * 2
    # bytes
    actual_size = Path(fp).stat().st_size
    if expected_size != actual_size:
        logging.error(
            f"Cannot process '{fp}'. Volume was expected to be of size '{expected_size}' but was '{actual_size}'. Please check data for corruption."
        )
        return

    # Determine output location and check for conflicts
    ofp = os.path.join(
        args.cwd, f"{os.path.basename(os.path.splitext(fp)[0])}-projection-top.png"
    )
    if os.path.exists(ofp) and os.path.isfile(ofp):
        # If file creation not forced, do not process volume, return
        if args.force == False:
            logging.info(f"File already exists. Skipping {ofp}.")
            return
        # Otherwise, user forced file generation
        else:
            logging.warning(f"FileExistsWarning - {ofp}. File will be overwritten.")

    # Calculate the number of bytes in a *single* slice of .RAW datafile
    # NOTE(tparker): This assumes that a unsigned 16-bit .RAW volume
    buffer_size = x * y * np.dtype("uint16").itemsize
    logging.debug(
        f"Allocated memory for a slice (i.e., buffer_size): {buffer_size} bytes"
    )

    if not args.verbose:
        pbar = tqdm(total=z, desc="Generating top-down projection")  # progress bar
    with open(fp, mode="rb", buffering=buffer_size) as ifp:
        # Load in the first slice
        byte_slice = ifp.read(buffer_size)  # Byte sequence
        try:
            np.zeros(y * x, dtype=np.uint16).reshape(y, x)
        except Exception as err:
            logging.error(err)
            return

        raw_image_data = np.zeros(y * x, dtype=np.uint16).reshape(y, x)
        # For each slice in the volume....
        while len(byte_slice) > 0:
            # Convert bytes to 16-bit values
            byte_sequence_max_values = np.frombuffer(byte_slice, dtype=np.uint16)
            # Create a 2-D array of the data that is analogous to the image
            byte_sequence_max_values = byte_sequence_max_values.reshape(y, x)
            # 'Squash' together the brightest values so far with the current slice
            raw_image_data = np.maximum(raw_image_data, byte_sequence_max_values)
            # # Read the next slice & update progress bar
            byte_slice = ifp.read(buffer_size)
            if not args.verbose:
                pbar.update(1)
        if not args.verbose:
            pbar.close()

        # Convert raw bytes to array of 16-bit values
        logging.debug(f"raw_image_data shape: {np.shape(raw_image_data)}")
        arr = np.frombuffer(raw_image_data, dtype=np.uint16)
        logging.debug(f"raw_image_data pixel count: {len(arr)}")
        # Change the array from a byte sequence to a 2-D array with the same dimensions as the image
        try:
            arr = raw_image_data
            array_buffer = arr.tobytes()
            pngImage = Image.new("I", arr.T.shape)
            pngImage.frombytes(array_buffer, "raw", "I;16")
            if not args.dryrun:
                pngImage.save(ofp)

        except Exception as err:
            logging.error(err)
            sys.exit(1)
        else:
            logging.debug(f"Saving top-down projection as '{ofp}'")


def get_side_projection(args, fp):
    """Generate a projection from the profile view a volume, using its maximum values per slice

    Args:
      args (Namespace): user-defined arguments
      fp (str): filepath for a .RAW volume

    """
    global font
    # Extract the resolution from .DAT file
    dat_fp = rawfp2datfp(fp)
    logging.debug(f"{dat_fp=}")
    x, y, z = dat.read(dat_fp)["dimensions"]
    logging.debug(f"Volume dimensions: {x}, {y}, {z}")

    # NOTE(tparker): Patch to skip volumes of unexpected size
    expected_size = x * y * z * 2
    # bytes
    actual_size = Path(fp).stat().st_size
    if expected_size != actual_size:
        if not args.force:
            logging.error(
                f"Cannot process '{fp}'. Volume was expected to be of size '{expected_size}' but was '{actual_size}'. Please check data for corruption."
            )
            return
        else:
            # Otherwise, find the slice index of the last complete slice
            size_delta = expected_size - actual_size
            # If the file is larger than expected, there is larger problems than
            # incomplete data, so do not process it
            if size_delta < 0:
                logging.error(
                    "Cannot process '{fp}'. Volume was larger than expected. Volume was expected to be of size '{expected_size}' but was '{actual_size}'. Please check data for corruption."
                )
            else:
                z_prime = math.floor(actual_size / (x * y * 2))
                logging.info(
                    f" Volume was expected to be of size '{expected_size}' but was '{actual_size}'. Please check data for corruption. Processing only '{z_prime}' of '{z}' slices."
                )
                z = z_prime

    # Determine output location and check for conflicts
    ofp = os.path.join(
        args.cwd, f"{os.path.basename(os.path.splitext(fp)[0])}-projection-side.png"
    )
    if os.path.exists(ofp) and os.path.isfile(ofp):
        # If file creation not forced, do not process volume, return
        if args.force == False:
            logging.info(f"File already exists. Skipping {ofp}.")
            return
        # Otherwise, user forced file generation
        else:
            logging.warning(f"FileExistsWarning - {ofp}. File will be overwritten.")

    # Calculate the number of bytes in a *single* slice of .RAW datafile
    # NOTE(tparker): This assumes that a unsigned 16-bit .RAW volume
    buffer_size = x * y * np.dtype("uint16").itemsize
    logging.debug(
        f"Allocated memory for a slice (i.e., buffer_size): {buffer_size} bytes"
    )

    if not args.verbose:
        pbar = tqdm(
            total=z,
            desc=f"Generating side-view projection for '{os.path.basename(fp)}'",
        )  # progress bar
    with open(fp, mode="rb", buffering=buffer_size) as ifp:

        # Load in the first slice
        byte_slice = ifp.read(buffer_size)  # Byte sequence
        raw_image_data = bytearray()
        # For each slice in the volume....
        while len(byte_slice) == buffer_size:
            # Convert bytes to 16-bit values
            byte_sequence_max_values = np.frombuffer(byte_slice, dtype=np.uint16)

            # Create a 2-D array of the data that is analogous to the image
            byte_sequence_max_values = byte_sequence_max_values.reshape(y, x)
            # 'Squash' the slice into a single row of pixels containing the highest value along the
            byte_sequence_max_values = np.amax(byte_sequence_max_values, axis=0)
            # Convert 16-bit values back to bytes
            byte_sequence_max_values = byte_sequence_max_values.tobytes()

            # Append the maximum values to the resultant image
            raw_image_data.extend(byte_sequence_max_values)
            # Read the next slice & update progress bar
            byte_slice = ifp.read(buffer_size)

            if not args.verbose:
                pbar.update(1)
        if not args.verbose:
            pbar.close()

        # Convert raw bytes to array of 16-bit values
        logging.debug(f"raw_image_data length: {len(raw_image_data)}")
        arr = np.frombuffer(raw_image_data, dtype=np.uint16)
        logging.debug(f"arr length: {len(arr)}")
        # Change the array from a byte sequence to a 2-D array with the same dimensions as the image
        try:
            logging.debug("Reshaping image")
            logging.debug(f"arr = arr.reshape([{x}, {z}])")
            arr = arr.reshape([x, z])
            logging.debug(f"array_buffer = arr.tobytes()")
            array_buffer = arr.tobytes()
            logging.debug(f'pngImage = Image.new("I", {arr.shape})')
            pngImage = Image.new("I", arr.shape)
            logging.debug(f"pngImage.frombytes(array_buffer, 'raw', \"I;16\")")
            pngImage.frombytes(array_buffer, "raw", "I;16")
            if not args.dryrun:
                logging.debug(f"pngImage.save(ofp)")
                pngImage.save(ofp)

            if "step" in args and args.step:
                try:
                    fill = (255, 0, 0, 225)
                    img = Image.open(ofp)
                    # Convert from grayscale to RGB
                    img = (
                        ImageMath.eval("im/256", {"im": img})
                        .convert("L")
                        .convert("RGBA")
                    )
                    draw = ImageDraw.Draw(img)

                    ascent, descent = font.getmetrics()
                    offset = (ascent + descent) // 2

                    _, height = img.size  # width is usused
                    slice_index = 0

                    while slice_index < height:
                        slice_index += args.step
                        # Adding text to current slice
                        # Getting the ideal offset for the font
                        # https://stackoverflow.com/questions/43060479/how-to-get-the-font-pixel-height-using-pil-imagefont
                        text_y = slice_index - offset
                        draw.text((110, text_y), str(slice_index), font=font, fill=fill)
                        # Add line
                        draw.line((0, slice_index, 100, slice_index), fill=fill)
                    if not args.dryrun:
                        img.save(ofp)
                except:
                    raise

        except Exception as err:
            logging.error(err)
            raise err
            sys.exit(1)
        else:
            logging.debug(f"Saving side-view projection as '{ofp}'")


def get_slice(args, fp):
    """Extract the Nth slice out of a .RAW volume

    Args:
      args (Namespace): user-defined arguments
      fp (str): (Default: midslice) filepath for a .RAW volume

    """
    # Extract the resolution from .DAT file
    dat_fp = rawfp2datfp(fp)
    logging.debug(f"{dat_fp=}")
    x, y, z = dat.read(dat_fp)["dimensions"]

    # Get the requested slice index
    i = int(math.floor(x / 2))  # set default to midslice
    # If index defined and has a value, update index
    if hasattr(args, "index"):
        if args.index is not None:
            i = args.index
    else:
        logging.info(f"Slice index not specified. Using midslice as default: '{i}'.")

    # Determine output location and check for conflicts
    ofp = os.path.join(
        args.cwd, f"{os.path.basename(os.path.splitext(fp)[0])}.s{str(i).zfill(5)}.png"
    )
    if os.path.exists(ofp) and os.path.isfile(ofp):
        # If file creation not forced, do not process volume, return
        if args.force == False:
            logging.info(f"File already exists. Skipping {ofp}.")
            return
        # Otherwise, user forced file generation
        else:
            logging.warning(f"FileExistsWarning - {ofp}. File will be overwritten.")

    # Calculate the number of bytes in a *single* slice of .RAW data file
    # NOTE(tparker): This assumes that an unsigned 16-bit .RAW volume
    buffer_size = x * y * np.dtype("uint16").itemsize

    # Calculate the index bounds for the bytearray of a slice
    # This byte array is a 1-D array of the image data for the current slice
    # The index defined
    if i < 0 or i > y - 1:
        logging.error(
            f"OutOfBoundsError - Index specified, '{i}' outside of dimensions of image. Image dimensions are ({x}, {y}). Slices are indexed from 0 to {y - 1}, inclusive."
        )
        sys.exit(1)
    start_byte = np.dtype("uint16").itemsize * x * i
    end_byte = np.dtype("uint16").itemsize * x * (i + 1)
    logging.debug(
        f"Relative byte indices for extracted slice: <{start_byte}, {end_byte}>"
    )
    logging.debug(
        f"Allocated memory for a slice (i.e., buffer_size): {buffer_size} bytes"
    )

    if not args.verbose:
        pbar = tqdm(total=z, desc=f"Extracting slice #{i}")  # progress bar
    with open(fp, mode="rb", buffering=buffer_size) as ifp:
        byte_slice = ifp.read(buffer_size)  # Byte sequence
        raw_byte_string = bytearray()
        # So long as there is data left in the .RAW, extract the next byte subset
        while len(byte_slice) > 0:
            ith_byte_sequence = byte_slice[start_byte:end_byte]
            raw_byte_string.extend(ith_byte_sequence)
            byte_slice = ifp.read(buffer_size)
            if not args.verbose:
                pbar.update(1)
        if not args.verbose:
            pbar.close()

    # Convert raw bytes to array of 16-bit values
    arr = np.frombuffer(raw_byte_string, dtype=np.uint16)
    # Change the array from a byte sequence to a 2-D array with the same dimensions as the image
    try:
        arr = arr.reshape([z, x])
        array_buffer = arr.tobytes()
        pngImage = Image.new("I", arr.T.shape)
        pngImage.frombytes(array_buffer, "raw", "I;16")
        if not args.dryrun:
            pngImage.save(ofp)
    except Exception as err:
        logging.error(err)
        sys.exit(1)
    else:
        logging.debug(f"Saving Slice #{i} as '{ofp}'")


def main(args):
    """Begin processing"""
    global font

    logging.debug(f"File(s) selected: {args.path}")
    # For each file provided...
    paths = args.path
    args.path = []
    logging.debug(f"Paths: {paths}")
    for fp in paths:
        logging.debug(f"Checking path '{fp}'")
        # Check if supplied 'file' is a file or a directory
        afp = os.path.abspath(fp)  # absolute path
        if not os.path.isfile(afp):
            logging.debug(f"Not a file '{fp}'")
            # If a directory, collect all contained .raw files and append to
            if os.path.isdir(afp):
                logging.debug(f"Is a directory '{fp}'")
                list_dirs = os.walk(fp)
                for root, dirs, files in list_dirs:
                    # Convert to fully qualified paths
                    files = [os.path.join(root, f) for f in files]
                    raw_files = [f for f in files if os.path.splitext(f)[1] == ".raw"]
                    logging.debug(f"Found .raw files {raw_files}")
                    for filename in raw_files:
                        logging.debug(f"Verifying '{filename}'")
                        # Since we traversed the path to find this file, it should exist
                        # This could cause a race condition if someone were to delete the
                        # file while this script was running

                        basename, extension = os.path.splitext(filename)
                        dat_filename = basename + ".dat"
                        # Only parse .raw files
                        if extension == ".raw":
                            # Check if it has a .dat
                            if not os.path.exists(dat_filename):
                                logging.warning(
                                    f"Missing '.dat' file: '{dat_filename}'"
                                )
                            elif not os.path.isfile(dat_filename):
                                logging.warning(
                                    f"Provided '.dat' is not a file: '{dat_filename}'"
                                )
                            else:
                                args.path.append(filename)
            else:
                logging.warning(f"Is not a file or directory: '{fp}'")
        else:
            basename, extension = os.path.splitext(fp)
            dat_filename = basename + ".dat"
            # Only parse .raw files
            if extension == ".raw":
                # Check if it has a .dat
                if not os.path.exists(dat_filename):
                    logging.warning(f"Missing '.dat' file: '{dat_filename}'")
                elif not os.path.isfile(dat_filename):
                    logging.warning(f"Provided '.dat' is not a file: '{dat_filename}'")
                else:
                    args.path.append(fp)

    args.path = list(set(args.path))
    logging.info(f"Found {len(args.path)} .raw file(s).")
    logging.debug(args.path)
    if "index" not in args and not args.projection:
        logging.warning(f"No action specified.")
    else:
        if not args.verbose:
            total_pbar = tqdm(total=len(args.path), desc="Total Progress")
        for fp in args.path:
            # Set working directory for file
            args.cwd = os.path.dirname(os.path.abspath(fp))
            if args.outdir is not None:
                args.cwd = os.path.realpath(args.outdir)
            fp = os.path.abspath(fp)

            # Format file size
            n_bytes = os.path.getsize(fp)
            if args.si:
                filesize = sizeof_fmt(n_bytes)
            else:
                filesize = f"{n_bytes} B"

            # Process files
            # Load font
            font_fp = "/".join(
                [
                    os.path.dirname(os.path.realpath(__file__)),
                    "assets",
                    "OpenSans-Regular.ttf",
                ]
            )
            logging.debug(f"Font filepath: '{font_fp}'")
            font = ImageFont.truetype(font_fp, args.font_size)
            logging.debug(f"Processing '{fp}' ({filesize})")
            if "index" in args and args.index is not None:
                if args.index is True:
                    args.index = None
                get_slice(args, fp)
                args.index = True  # re-enable slice for the next volume
            if args.projection is not None:
                if "side" in args.projection:
                    get_side_projection(args, fp)
                if "top" in args.projection:
                    get_top_down_projection(args, fp)

            if not args.verbose:
                total_pbar.update()
        if not args.verbose:
            total_pbar.close()
