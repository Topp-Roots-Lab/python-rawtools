#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""NSIHDRv1 to RAW Batch Converter"""
import logging
import os
import re
import sys

import numpy as np
from tqdm import tqdm

from rawtools import dat
from rawtools.convert import scale

# Global bounds for initial and target ranges per NSI project file
INITIAL_LOWER_BOUND = None
INITIAL_UPPER_BOUND = None
TARGET_LOWER_BOUND = None
TARGET_UPPER_BOUND = None

# TODO(tparker): Replace with library version of this
def write_metadata(args, metadata):
  """Generates a .dat file from information gathered from an .nsihdr file

  NOTE(tparker): Temporarily, I am writing the minimum and maximum values found
  in the 32-bit float version of the files in case we ever need to convert the
  uint16 version back to float32.

  Args:
    args (ArgumentParser): user arguments from `argparse`
    metadata (dict): dictionary of metadata created from reading .nsihdr file
  """
  ObjectFileName = args.output
  resolution = ' '.join(metadata['dimensions'])
  slice_thickness = ' '.join([ str(rr) for rr in metadata['resolution_rounded'] ])
  dat_filepath = f'{os.path.splitext(args.output)[0]}.dat'
  output_string = f"""ObjectFileName: {ObjectFileName}\nResolution:     {resolution}\nSliceThickness: {slice_thickness}\nFormat:         {metadata['bit_depth_type']}\nObjectModel:    {metadata['ObjectModel']}"""

  dat.write(dat_filepath, metadata['dimensions'], metadata['resolution_rounded'])
  # with open(dat_filepath, 'w') as ofp:
  #   print(f'Generating {dat_filepath}')
  #   ofp.write(output_string)

  bounds_filepath = os.path.join(args.cwd, f'{os.path.splitext(args.output)[0]}.float32.range')
  with open(bounds_filepath, 'w') as ofp:
    print(f'Generating {bounds_filepath}')
    bounds = f'{INITIAL_LOWER_BOUND} {INITIAL_UPPER_BOUND}'
    ofp.write(bounds)

def read_nsihdr(args, fp):
  """Collects relative metadata from .nsihdr file

  Args:
    fp (str): Input filepath to an .nsihdr file

  Returns:
    dict: metadata about NSI project
  """
  global INITIAL_LOWER_BOUND
  global INITIAL_UPPER_BOUND

  with open(fp, 'r') as ifp:
    document = ifp.readlines()

    nsidat_pattern = r'(?P<prefix><Name>)(?P<filename>.*.nsidat)'
    detector_distance_pattern = r'<source to detector distance>(?P<value>[\d\.]+)'
    table_distance_pattern = r'<source to table distance>(?P<value>[\d\.]+)'
    bit_depth_pattern = r'(?P<prefix><bit depth>)(?P<value>\d+)'
    dimensions_pattern = r'(?P<prefix><resolution>)(?P<x>\d+)\s+(?P<num_slices>\d+)\s+(?P<z>\d+)'
    data_range_pattern = r'<DataRange>\s+(?P<lower_bound>\-?\d+\.\d+)\s+(?P<upper_bound>\-?\d+\.\d+)'

    source_to_detector_distance = None
    source_to_table_distance = None
    bit_depth = None
    nsidats = []
    for line in document:
      nsidat_query = re.search(nsidat_pattern, line)
      if nsidat_query:
        nsidats.append(nsidat_query.group('filename'))

      detector_query = re.search(detector_distance_pattern, line)
      if detector_query:
        source_to_detector_distance = float(detector_query.group('value'))

      table_query = re.search(table_distance_pattern, line)
      if table_query:
        source_to_table_distance = float(table_query.group('value'))

      bit_depth_query = re.search(bit_depth_pattern, line)
      if bit_depth_query:
        bit_depth = int(bit_depth_query.group('value'))

      dimensions_query = re.search(dimensions_pattern, line)
      if dimensions_query:
        dimensions = [ dimensions_query.group('x'), dimensions_query.group('z'), dimensions_query.group('num_slices') ]

      # Check if the .nsihdr already contains the data range
      # If it exists, we only have to read the .nsidat files once instead of twice
      data_range_query = re.search(data_range_pattern, line)
      if data_range_query:
        INITIAL_LOWER_BOUND = float(data_range_query.group('lower_bound'))
        INITIAL_UPPER_BOUND = float(data_range_query.group('upper_bound'))

      # Temporarily set pitch as 0.127, as it should not change until we get a
      # new detector
      pitch = 0.127

      # TODO(tparker): As far as I am aware, the data will always be of type DENSITY
      ObjectModel = 'DENSITY'

    resolution = ( pitch / source_to_detector_distance ) * source_to_table_distance
    resolution_rounded = round(resolution, 4)
    nsidats.sort() # make sure that the files are in alphanumeric order

    return {
      "datafiles": nsidats,
      "source_to_detector_distance": source_to_detector_distance,
      "source_to_table_distance": source_to_table_distance,
      "pitch": pitch,
      "resolution": resolution,
      "resolution_rounded": [resolution_rounded]*3,
      "bit_depth": bit_depth,
      "zoom_factor": round(source_to_detector_distance / source_to_table_distance, 2),
      "bit_depth_type": dat.bitdepth(bit_depth),
      "ObjectModel": ObjectModel,
      "dimensions": dimensions
    }

def set_initial_bounds(metadata):
  """Scans .nsidat files for minimum and maximum values and sets them globally

  Args:
    files (list of str): list of filepaths to .nsidat files
  
  """
  global INITIAL_LOWER_BOUND
  global INITIAL_UPPER_BOUND

  files = metadata['datafiles']
  for f in tqdm(files, desc=f"Determining bounds for {metadata['nsihdr_fp']}"):
    input_filepath = os.path.join(args.cwd, f)
    with open(input_filepath, mode='rb') as ifp:
      # Assume 32-bit floating point value
      # NOTE(tparker): This may not be true for all volumes
      df = np.fromfile(ifp, dtype='float32')

      if INITIAL_LOWER_BOUND is None:
        INITIAL_LOWER_BOUND = df.min()
      else:
        INITIAL_LOWER_BOUND = min(INITIAL_LOWER_BOUND, df.min())
      if INITIAL_UPPER_BOUND is None:
        INITIAL_UPPER_BOUND = df.max()
      else:
        INITIAL_UPPER_BOUND = max(INITIAL_UPPER_BOUND, df.max())

      logging.debug(f'Current bounds: [{INITIAL_LOWER_BOUND}, {INITIAL_UPPER_BOUND}]')
  print(f'Bounds set: [{INITIAL_LOWER_BOUND}, {INITIAL_UPPER_BOUND}]')

def process(args, metadata):
  """Coalesces and converts .nsidat files to a single .raw

  Args:
    args (ArgumentParser): user arguments from `argparse`
    metadata (dict): dictionary of metadata created from reading .nsihdr file
  """
  # Since the .raw file is generated by appending the data to the end of a file, you have
  # to remove any existing .raw volume if generation is forced
  try:
    # Determine output location and check for conflicts
    if os.path.exists(args.output) and os.path.isfile(args.output):
      # If file creation not forced, do not process volume, return
      if args.force == False:
        logging.info(f"File already exists: '{args.output}.' Aborting...")
        sys.exit(0)
      # Otherwise, remove the existing .raw volume
      else:
        logging.info(f"File already exists. Deleting '{args.output}'.")
        os.remove(args.output)
  except Exception as err:
    logging.error(err)
    raise

  pbar = tqdm(total = len(metadata['datafiles']), desc=f'Generating {args.output}')
  for f in metadata['datafiles']:
    input_filepath = os.path.join(args.cwd, f)
    df = None
    with open (input_filepath, mode='rb') as ifp:
      df = np.fromfile(ifp, dtype='float32') # Assume 32-bit floating point value, but this may not be true for all volumes

    sdf = scale(df, INITIAL_LOWER_BOUND, INITIAL_UPPER_BOUND, TARGET_LOWER_BOUND, TARGET_UPPER_BOUND).astype('uint16')
    with open(args.output, 'ab') as ofp:
      sdf.tofile(ofp)
      pbar.update(1)
  pbar.close()

def main(args):
  logging.debug(f'Converting {args.files}')
  for f in args.files:
    # Set working directory for files
    args.cwd = os.path.dirname(f)
    # Set filename being processed
    args.filename = f
    project_metadata = read_nsihdr(args, f)
    project_metadata['nsihdr_fp'] = args.filename

    # Set bounds
    TARGET_LOWER_BOUND = 0
    TARGET_UPPER_BOUND = (2**project_metadata['bit_depth'] - 1)
    try:
      args.output = os.path.join(args.cwd, f'{os.path.basename(os.path.splitext(args.filename)[0])}.raw')
      # Determine output location and check for conflicts
      if os.path.exists(args.output) and os.path.isfile(args.output):
        # If file creation not forced, do not process volume, return
        if args.force == False:
          logging.info(f"File already exists. Skipping {args.output}.")
          sys.exit(0)
        # Otherwise, user forced file generation
        else:
          logging.warning(f"FileExistsWarning - {args.output}. File will be overwritten.")
      
      # Base case: if the data range was found in the .nsihdr, no need to check .nsidat files
      if INITIAL_LOWER_BOUND is not None and INITIAL_UPPER_BOUND is not None:
        logging.info(f'Bounds located in {args.filename}. Bounds set to [{INITIAL_LOWER_BOUND}, {INITIAL_UPPER_BOUND}].')
      else:
        set_initial_bounds(project_metadata)

      # Generate .RAW volume
      process(args, project_metadata)
      # Create .dat & .range files
      write_metadata(args, project_metadata)
    except Exception as err:
      logging.error(err)
      raise

    # Reset bounds after file has been processed
    INITIAL_LOWER_BOUND = None
    INITIAL_UPPER_BOUND = None
    TARGET_LOWER_BOUND = None
    TARGET_UPPER_BOUND = None