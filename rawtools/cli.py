"""Console script for rawtools."""
import argparse
import sys
from importlib.metadata import version
from multiprocessing import cpu_count

from rawtools import convert, generate, log, qualitycontrol, raw2img

__version__ = version('rawtools')

def main():
    """Console script for rawtools."""
    return 0

def raw_convert():
    supported_output_formats = ['uint16']
    supported_input_formats = ['float32']
    description='Convert .raw 3d volume file to typical image format slices'

    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-V", "--version", action="version", version=f'%(prog)s {__version__}')
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity")
    parser.add_argument("-t", "--threads", type=int, default=cpu_count(), help=f"Maximum number of threads dedicated to processing.")
    parser.add_argument("-f", '--force', action="store_true", help="Force file creation. Overwrite any existing files.")
    parser.add_argument("--format", default='uint16', help=f"Desired output .RAW format. Supported formats: {supported_output_formats}")
    parser.add_argument("path", metavar='PATH', type=str, nargs='+', help=f"Input directory to process. Supported formats: {supported_input_formats}")
    args = parser.parse_args()

    # Check for unsupported formats
    if args.format not in supported_output_formats:
        raise ValueError(f"Unsupported format, '{args.format}' specified. Please specify a supported format: {supported_output_formats}")

    # Set up logging
    args.module_name = 'convert'
    log.configure(args)

    # Make sure user does not request more CPUs can available
    if args.threads > cpu_count():
        args.threads = cpu_count()

    # Change format to always be lowercase
    args.format = args.format.lower()
    args.path = list(set(args.path)) # remove any duplicates

    # Run module
    convert.main(args)

def raw_generate():
    description = "Convert .raw 3d volume file to typical image format slices"

    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-V", "--version", action="version", version=f'%(prog)s {__version__}')
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity")
    parser.add_argument('-t', "--threads", type=int, default=cpu_count(), help=f"Maximum number of threads dedicated to processing.")
    parser.add_argument('--force', action="store_true", help="Force file creation. Overwrite any existing files.")
    parser.add_argument("path", metavar='PATH', type=str, nargs='+', help='Image filepath(s)')
    args = parser.parse_args()

    args.module_name = 'generate'
    log.configure(args)

    generate.main(args)

def raw_nsihdr():
    description = "This tool converts a NSI project from 32-bit float to 16-bit unsigned integer format."

    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-V", "--version", action="version", version=f'%(prog)s {__version__}')
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Increase output verbosity")
    parser.add_argument("-f", "--force", action="store_true", default=False, help="Force file creation. Overwrite any existing files.")
    parser.add_argument("--gui", action="store_true", default=False, help="(Experimental) Enable GUI")
    parser.add_argument('path', metavar='PATH', type=str, nargs="+", help='List of .nsihdr files')
    args = parser.parse_args()

    args.module_name = 'nsihdr'
    log.configure(args)

    # Use a GUI to select the source directory
    if args.gui == True:
        from rawtools.gui import nsihdr
        nsihdr.App(args)
    # Otherwise, assume CLI use
    else:
        from rawtools import nsihdr
        nsihdr.main(args)

def raw_qc():
    """Quality control tools"""
    description = "Check the quality of a .RAW volume by extracting a slice or generating a projection. Requires a .RAW and .DAT for each volume."

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-V", "--version", action="version",
                        version=f'%(prog)s {__version__}')
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Increase output verbosity")
    parser.add_argument("-f", "--force", action="store_true", default=False,
                        help="Force file creation. Overwrite any existing files.")
    parser.add_argument("--si", action="store_true", default=False,
                        help="Print human readable sizes (e.g., 1 K, 234 M, 2 G)")
    parser.add_argument("-n", '--dry-run', dest='dryrun', action="store_true",
                        help="Perform a trial run. Do not create image files, but logs will be updated.")
    parser.add_argument("-p", "--projection", action="store", nargs='+',
                        help="Generate projection using maximum values for each slice. Available options: [ 'top', 'side' ].")
    parser.add_argument("--scale", dest="step", const=100, action="store", nargs='?', default=argparse.SUPPRESS, type=int,
                        help="Add scale on left side of a side projection. Step is the number of slices between each label. (default: 100)")
    parser.add_argument("-s", "--slice", dest='index', const=True, nargs='?', type=int,
                        default=argparse.SUPPRESS, help="Extract a slice from volume's side view. (default: floor(x/2))")
    parser.add_argument("--font-size", dest="font_size", action="store",
                        type=int, default=24, help="Font size of labels of scale.")
    parser.add_argument("-o", "--outdir", action="store", help="Output folder to store all generated files. If not provided, each file will be placed in the folder of the source data.")
    parser.add_argument("path", metavar='PATH', type=str, nargs='+',
                        help='Filepath to a .RAW or path to a directory that contains .RAW files.')
    args = parser.parse_args()

    args.module_name = 'qc'
    log.configure(args)

    qualitycontrol.main(args)


def raw_image():
    description='Convert .raw 3d volume file to typical image format slices'
    parser = argparse.ArgumentParser(description=description,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity")
    parser.add_argument("-V", "--version", action="version", version=f'%(prog)s {__version__}')
    parser.add_argument("-t", "--threads", type=int, default=cpu_count(), help=f"Maximum number of threads dedicated to processing.")
    parser.add_argument("-f", '--force', action="store_true", help="Force file creation. Overwrite any existing files.")
    parser.add_argument("-n", '--dry-run', dest='dryrun', action="store_true", help="Perform a trial run. Do not create image files, but logs will be updated.")
    parser.add_argument("--format", default='png', help="Set image filetype. Availble options: ['png', 'tif']")
    parser.add_argument("path", metavar='PATH', type=str, nargs=1, help='Input directory to process')
    args = parser.parse_args()

    # Make sure user does not request more CPUs can available
    if args.threads > cpu_count():
        args.threads = cpu_count()

    # Change format to always be lowercase
    args.format = args.format.lower()
    args.path = list(set(args.path)) # remove any duplicates

    args.module_name = 'raw2img'
    log.configure(args)

    raw2img.main(args)

if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
