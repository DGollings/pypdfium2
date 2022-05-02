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
import subprocess
from urllib import request
from os.path import join, abspath, dirname
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, dirname(dirname(abspath(__file__))))
from pl_setup.packaging_base import (
    DataTree,
    VersionFile,
    PlatformNames,
    run_cmd,
    extract_version,
    call_ctypesgen,
)


ReleaseRepo = "https://github.com/bblanchon/pdfium-binaries"
ReleaseURL = ReleaseRepo + "/releases/download/chromium%2F"
ReleaseExtension = "tgz"
ReleaseNames = {
    PlatformNames.darwin_x64    : 'pdfium-mac-x64',
    PlatformNames.darwin_arm64  : 'pdfium-mac-arm64',
    PlatformNames.linux_x64     : 'pdfium-linux-x64',
    PlatformNames.linux_x86     : 'pdfium-linux-x86',
    PlatformNames.linux_arm64   : 'pdfium-linux-arm64',
    PlatformNames.linux_arm32   : 'pdfium-linux-arm',
    PlatformNames.musllinux_x64 : 'pdfium-linux-musl-x64',
    PlatformNames.musllinux_x86 : 'pdfium-linux-musl-x86',
    PlatformNames.windows_x64   : 'pdfium-win-x64',
    PlatformNames.windows_x86   : 'pdfium-win-x86',
    PlatformNames.windows_arm64 : 'pdfium-win-arm64',
}


def _set_versions(*versions_list):
    
    with open(VersionFile, 'r') as fh:
        content = fh.read()
    
    for variable, current_ver, new_ver in versions_list:
        
        template = "%s = %s"
        previous = template % (variable, current_ver)
        updated = template % (variable, new_ver)
        
        print("'%s' -> '%s'" % (previous, updated))
        assert content.count(previous) == 1
        content = content.replace(previous, updated)
    
    with open(VersionFile, 'w') as fh:
        fh.write(content)


def get_latest_version():
    
    git_ls = run_cmd(['git', 'ls-remote', '%s.git' % ReleaseRepo], cwd=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    
    git_ls = git_ls.stdout.decode('UTF-8')
    tag = git_ls.split('\t')[-1].replace('\n', '')
    version = int(tag.split('/')[-1])
    
    return version


def handle_versions(latest_version):
    
    v_minor = extract_version('V_MINOR')
    v_libpdfium = extract_version('V_LIBPDFIUM')
    
    if v_libpdfium < latest_version:
        print("New PDFium build")
        _set_versions(
            ('V_MINOR', v_minor, v_minor+1),
            ('V_LIBPDFIUM', v_libpdfium, latest_version),
        )
    
    else:
        print("No new PDFium build - will re-create bindings without incrementing version")


def clear_data(download_files):
    for pl_dir in download_files:
        if os.path.isdir(pl_dir):
            shutil.rmtree(pl_dir)


def _get_package(args):
    
    dirpath, file_url, file_path = args
    print("'%s' -> '%s'" % (file_url, file_path))
    
    try:
        request.urlretrieve(file_url, file_path)
    except Exception:
        traceback.print_exc()
        return
    
    return dirpath, file_path


def download_releases(latest_version, download_files):
    
    base_url = "%s%s/" % (ReleaseURL, latest_version)
    args = []
    
    for dirpath, arcname in download_files.items():
        if not os.path.exists(dirpath):
            os.makedirs(dirpath)
        filename = "%s.%s" % (arcname, ReleaseExtension)
        file_url = base_url + filename
        file_path = join(dirpath, filename)
        args.append( (dirpath, file_url, file_path) )
    
    archives = {}
    with ThreadPoolExecutor( len(args) ) as pool:
        for output in pool.map(_get_package, args):
            if output is not None:
                dirpath, file_path = output
                archives[dirpath] = file_path
    
    return archives


def unpack_archives(archives):
    
    for file in archives.values():
        
        if ReleaseExtension == 'tgz':
            arc_opener = tarfile.open
        else:
            raise ValueError("Unknown archive extension '%s'" % ReleaseExtension)
        
        extraction_path = join(os.path.dirname(file), 'build_tar')
        with arc_opener(file) as archive:
            archive.extractall(extraction_path)
        
        os.remove(file)


def generate_bindings(archives): 
    
    for platform_dir in archives.keys():
        
        build_dir = join(platform_dir,'build_tar')
        bin_dir = join(build_dir,'lib')
        dirname = os.path.basename(platform_dir)
        
        if dirname.startswith('windows'):
            target_name = 'pdfium.dll'
            bin_dir = join(build_dir,'bin')
        elif dirname.startswith('darwin'):
            target_name = 'pdfium.dylib'
        elif 'linux' in dirname:
            target_name = 'pdfium'
        else:
            raise ValueError("Unknown platform directory name '%s'" % dirname)
        
        items = os.listdir(bin_dir)
        assert len(items) == 1
        
        shutil.move(join(bin_dir, items[0]), join(platform_dir, target_name))
        
        call_ctypesgen(platform_dir, join(build_dir,'include'))
        shutil.rmtree(build_dir)


def get_download_files(platforms):
    
    avail_keys = [k for k in ReleaseNames.keys()]
    if platforms is None:
        platforms = avail_keys
    
    download_files = {}
    for pl_name in platforms:
        if pl_name in ReleaseNames:
            download_files[ join(DataTree, pl_name) ] = ReleaseNames[pl_name]
        else:
            raise ValueError("Unknown platform name '%s'. Available keys are %s." % (pl_name, avail_keys))
    
    return download_files


def main(platforms):
    
    download_files = get_download_files(platforms)
    
    latest_version = get_latest_version()
    handle_versions(latest_version)
    clear_data(download_files)
    
    archives = download_releases(latest_version, download_files)
    unpack_archives(archives)
    generate_bindings(archives)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description = "Download pre-built PDFium packages and generate bindings",
    )
    parser.add_argument(
        '--platforms', '-p',
        metavar = 'P',
        nargs = '*',
    )
    return parser.parse_args(argv)


def run_cli(argv=sys.argv[1:]):
    args = parse_args(argv)
    return main(args.platforms)


if __name__ == '__main__':
    run_cli()