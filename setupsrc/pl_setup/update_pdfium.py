#! /usr/bin/env python3
# SPDX-FileCopyrightText: 2022 geisserml <geisserml@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR BSD-3-Clause

# Download the PDFium binaries and generate ctypes bindings

import os
import sys
import shutil
import tarfile
import argparse
import traceback
import functools
from urllib import request
from os.path import join, abspath, dirname
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, dirname(dirname(abspath(__file__))))
from pl_setup.packaging_base import (
    DataTree,
    VerNamespace,
    ReleaseNames,
    BinaryPlatforms,
    ReleaseURL,
    HostPlatform,
    set_version,
    get_latest_version,
    call_ctypesgen,
)

AutoPlatformId = "auto"


def handle_versions(latest):
    
    v_libpdfium = VerNamespace["V_LIBPDFIUM"]
    is_sourcebuild = VerNamespace["IS_SOURCEBUILD"]
    
    if is_sourcebuild:
        print("Switching from sourcebuild to pre-built binaries.")
        set_version("IS_SOURCEBUILD", False)
    if v_libpdfium != latest:
        set_version("V_LIBPDFIUM", latest)


def clear_data(download_files):
    for pl_dir in download_files:
        if os.path.isdir(pl_dir):
            shutil.rmtree(pl_dir)


def _get_package(robust, args):
    
    dirpath, file_url, file_path = args
    print("'%s' -> '%s'" % (file_url, file_path))
    
    try:
        request.urlretrieve(file_url, file_path)
    except Exception:
        if robust:
            traceback.print_exc()
            return
        else:
            raise
    
    return dirpath, file_path


def download_releases(latest_version, download_files, robust):
    
    base_url = "%s%s/" % (ReleaseURL, latest_version)
    args_list = []
    
    for dirpath, arcname in download_files.items():
        if not os.path.exists(dirpath):
            os.makedirs(dirpath)
        filename = "%s.%s" % (arcname, "tgz")
        file_url = base_url + filename
        file_path = join(dirpath, filename)
        args_list.append( (dirpath, file_url, file_path) )
    
    archives = {}
    with ThreadPoolExecutor(max_workers=len(args_list)) as pool:
        func = functools.partial(_get_package, robust)
        for output in pool.map(func, args_list):
            if output is not None:
                dirpath, file_path = output
                archives[dirpath] = file_path
    
    return archives


def unpack_archives(archives):
    for file in archives.values():
        extraction_path = join(os.path.dirname(file), "build_tar")
        with tarfile.open(file) as archive:
            archive.extractall(extraction_path)
        os.remove(file)


def generate_bindings(archives):
    
    for platform_dir in archives.keys():
        
        build_dir = join(platform_dir,"build_tar")
        bin_dir = join(build_dir, "lib")
        dirname = os.path.basename(platform_dir)
        
        if dirname.startswith("windows"):
            target_name = "pdfium.dll"
            bin_dir = join(build_dir, "bin")
        elif dirname.startswith("darwin"):
            target_name = "pdfium.dylib"
        elif "linux" in dirname:
            target_name = "pdfium"
        else:
            raise ValueError("Unknown platform directory name '%s'" % dirname)
        
        items = os.listdir(bin_dir)
        assert len(items) == 1
        
        shutil.move(join(bin_dir, items[0]), join(platform_dir, target_name))
        
        call_ctypesgen(platform_dir, join(build_dir, "include"))
        shutil.rmtree(build_dir)


def get_download_files(platforms):
    download_files = {}
    for pl_name in platforms:
        if pl_name == AutoPlatformId:
            pl_name = HostPlatform().get_name()
        download_files[ join(DataTree, pl_name) ] = ReleaseNames[pl_name]
    return download_files


def main(platforms, robust=False):
    
    download_files = get_download_files(platforms)
    
    latest = get_latest_version()
    handle_versions(str(latest))
    clear_data(download_files)
    
    archives = download_releases(latest, download_files, robust)
    unpack_archives(archives)
    generate_bindings(archives)


def parse_args(argv):
    platform_choices = (AutoPlatformId, *BinaryPlatforms)
    parser = argparse.ArgumentParser(
        description = "Download pre-built PDFium packages and generate bindings.",
    )
    parser.add_argument(
        "--platforms", "-p",
        nargs = "+",
        metavar = "identifier",
        choices = platform_choices,
        default = BinaryPlatforms,
        help = "The platform(s) to include. Available platform identifiers are %s. `auto` represents the current host platform." % (platform_choices, ),
    )
    parser.add_argument(
        "--robust",
        action = "store_true",
        help = "Skip missing binaries instead of raising an exception.",
    )
    return parser.parse_args(argv)


def run_cli(argv=sys.argv[1:]):
    args = parse_args(argv)
    main(
        args.platforms,
        robust = args.robust,
    )


if __name__ == "__main__":
    run_cli()
