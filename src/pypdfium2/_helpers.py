# SPDX-FileCopyrightText: 2021 geisserml <geisserml@gmail.com>
# SPDX-License-Identifier: Apache-2.0

import math
import ctypes
import traceback
from typing import Optional
from PIL import Image
from os.path import abspath


import pypdfium2 as pdfium
from pypdfium2._exceptions import *
from pypdfium2._constants import *


class PdfContext:
    """
    Context manager to open (and automatically close again) a PDFium document
    from a file path.
    
    Parameters:
        
        file_path:
            File path string to a PDF document.
        
        password:
            A password to unlock the document, if encrypted.
    
    Returns:
        ``FPDF_DOCUMENT``
    """
    
    def __init__(self, file_path: str, password: Optional[str] = None):
        self.file_path = abspath(file_path)
        self.password = password
    
    def __enter__(self) -> pdfium.FPDF_DOCUMENT:
        
        self.pdf = pdfium.FPDF_LoadDocument(self.file_path, self.password)
        
        if pdfium.FPDF_GetPageCount(self.pdf) < 1:
            raise PageCountInvalidError("No pages could be recognised.")
        
        return self.pdf
    
    def __exit__(self, exc_type, exc_value, exc_traceback):
        pdfium.FPDF_CloseDocument(self.pdf)
        if exc_type is not None:
            print(exc_traceback)
            raise exc_type(exc_value)


def _translate_rotation(rotation: int):
    if rotation == 0:
        return 0
    elif rotation == 90:
        return 1
    elif rotation == 180:
        return 2
    elif rotation == 270:
        return 3


def render_page(
        pdf: pdfium.FPDF_DOCUMENT,
        page_index: int,
        *,
        scale: float = 1,
        rotation: int = 0,
        background_colour: int = 0xFFFFFFFF,
        render_annotations: bool = True,
        optimise_mode: OptimiseMode = OptimiseMode.lcd_display,
    ) -> Image.Image:
    """
    Rasterise a PDF page using PDFium.
    
    Parameters:
        
        pdf:
            A PDFium document.
        
        page_index:
            Zero-based index of the page to render.
        
        scale:
            
            Define the quality (or size) of the image.
            
            By default, one PDF point (1/72in) is rendered to 1x1 pixel. This factor scales the
            number of pixels that represent one point.
            
            Higher values increase quality, file size and rendering duration, while lower values
            reduce them.
            
            Note that UserUnit is not taken into account, so if you are using PyPDFium2 in
            conjunction with an other PDF library, you may want to check for a possible
            ``/UserUnit`` in the page dictionary and multiply this scale factor with it.
        
        rotation:
            Rotate the page by 90, 180, or 270 degrees. Value 0 means no rotation.
        
        background_colour:
            A 32-bit colour value in 8888 ARGB format. Defaults to white (``0xFFFFFFFF``).
        
        render_annotations:
            Whether to render page annotations.
        
        optimise_mode:
            Optimise rendering for LCD displays or for printing.
    
    Returns:
        :class:`PIL.Image.Image`
    """
    
    page_count = pdfium.FPDF_GetPageCount(pdf)
    if not 0 <= page_index < page_count:
        raise PageIndexError(f"Page index {page_index} is out of bounds for document with {page_count} pages.")
    
    page = pdfium.FPDF_LoadPage(pdf, page_index)
    
    width  = math.ceil(pdfium.FPDF_GetPageWidthF(page)  * scale)
    height = math.ceil(pdfium.FPDF_GetPageHeightF(page) * scale)
    
    bitmap = pdfium.FPDFBitmap_Create(width, height, 0)
    pdfium.FPDFBitmap_FillRect(bitmap, 0, 0, width, height, background_colour)
    
    render_flags = 0x00
    if render_annotations:
        render_flags |= pdfium.FPDF_ANNOT
    
    if optimise_mode is OptimiseMode.none:
        pass
    elif optimise_mode is OptimiseMode.lcd_display:
        render_flags |= pdfium.FPDF_LCD_TEXT
    elif optimise_mode is OptimiseMode.printing:
        render_flags |= pdfium.FPDF_PRINTING
    else:
        raise ValueError(f"Invalid optimise_mode {optimise_mode}")
    
    pdfium.FPDF_RenderPageBitmap(
        bitmap,
        page,
        0, 0,
        width, height,
        _translate_rotation(rotation),
        render_flags,
    )
    
    cbuffer = pdfium.FPDFBitmap_GetBuffer(bitmap)
    buffer = ctypes.cast(cbuffer, ctypes.POINTER(ctypes.c_ubyte * (width * height * 4)))
    
    pil_image = Image.frombuffer("RGBA", (width, height), buffer.contents, "raw", "BGRA", 0, 1)
    
    if bitmap is not None:
        pdfium.FPDFBitmap_Destroy(bitmap)
    pdfium.FPDF_ClosePage(page)
    
    return pil_image
