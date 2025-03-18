/*
 * This file is part of the rc_genicam_api package.
 *
 * Copyright (c) 2019 Roboception GmbH
 * All rights reserved
 *
 * Author: Heiko Hirschmueller
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 * this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimer in the documentation
 * and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its contributors
 * may be used to endorse or promote products derived from this software without
 * specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

#include "image_store.h"
#include "pixel_formats.h"

#include <exception>

#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <limits>
#include <algorithm>

#ifdef INCLUDE_PNG
#include <png.h>
#endif

#ifdef _WIN32
#undef min
#undef max
#endif

namespace rcg
{

std::string ensureNewFileName(std::string name)
{
  // check if given name is already used

  std::ifstream file(name);

  if (file.is_open())
  {
    file.close();

    // split name in prefix and suffix

    std::string suffix;

    size_t i=name.rfind('.');
    if (i != name.npos && name.size()-i <= 4)
    {
      suffix=name.substr(i);
      name=name.substr(0, i);
    }

    // add number for finding name that is nor used

    int n=1;
    while (n < 100)
    {
      std::ostringstream s;
      s << name << "_" << n << suffix;

      file.open(s.str());
      if (!file.is_open())
      {
        name=s.str();
        break;
      }

      file.close();
      n++;
    }
  }

  return name;
}

namespace
{

class IOException : public std::exception
{
  public:

    IOException(const std::string &_msg) { msg=_msg; }
    virtual const char *what() const noexcept { return msg.c_str(); }

  private:

    std::string msg;
};

std::string storeImagePNM(const std::string &name, const rcg::Image &image, size_t yoffset,
  size_t height)
{
  size_t width=image.getWidth();
  size_t real_height=image.getHeight();

  if (height == 0) height=real_height;

  yoffset=std::min(yoffset, real_height);
  height=std::min(height, real_height-yoffset);

  const unsigned char *p=static_cast<const unsigned char *>(image.getPixels());

  size_t px=image.getXPadding();

  uint64_t format=image.getPixelFormat();
  std::string full_name;

  switch (format)
  {
    case Mono8: // store 8 bit monochrome image
    case Confidence8:
    case Error8:
      {
        full_name=ensureNewFileName(name+".pgm");
        std::ofstream out(full_name, std::ios::binary);

        out << "P5" << std::endl;
        out << width << " " << height << std::endl;
        out << 255 << "\n";

        std::streambuf *sb=out.rdbuf();

        p+=(width+px)*yoffset;
        for (size_t k=0; k<height && out.good(); k++)
        {
          for (size_t i=0; i<width; i++)
          {
            sb->sputc(static_cast<char>(*p++));
          }

          p+=px;
        }

        out.close();
      }
      break;

    case Mono16:
    case Coord3D_C16: // store 16 bit monochrome image
      {
        full_name=ensureNewFileName(name+".pgm");
        std::ofstream out(full_name, std::ios::binary);

        out << "P5" << std::endl;
        out << width << " " << height << std::endl;
        out << 65535 << "\n";

        std::streambuf *sb=out.rdbuf();

        // copy image data, pgm is always big endian

        p+=(2*width+px)*yoffset;
        if (image.isBigEndian())
        {
          for (size_t k=0; k<height && out.good(); k++)
          {
            for (size_t i=0; i<width; i++)
            {
              sb->sputc(static_cast<char>(*p++));
              sb->sputc(static_cast<char>(*p++));
            }

            p+=px;
          }
        }
        else
        {
          for (size_t k=0; k<height && out.good(); k++)
          {
            for (size_t i=0; i<width; i++)
            {
              sb->sputc(static_cast<char>(p[1]));
              sb->sputc(static_cast<char>(p[0]));
              p+=2;
            }

            p+=px;
          }
        }

        out.close();
      }
      break;

    case YCbCr411_8: // convert and store as color image
      {
        full_name=ensureNewFileName(name+".ppm");
        std::ofstream out(full_name, std::ios::binary);

        out << "P6" << std::endl;
        out << width << " " << height << std::endl;
        out << 255 << "\n";

        std::streambuf *sb=out.rdbuf();

        size_t pstep=(width>>2)*6+px;
        p+=pstep*yoffset;
        for (size_t k=0; k<height && out.good(); k++)
        {
          for (size_t i=0; i<width; i+=4)
          {
            uint8_t rgb[12];
            rcg::convYCbCr411toQuadRGB(rgb, p, static_cast<int>(i));

            for (int j=0; j<12; j++)
            {
              sb->sputc(static_cast<char>(rgb[j]));
            }
          }

          p+=pstep;
        }

        out.close();
      }
      break;

    default:
      throw IOException(std::string("storeImage(): Unknown pixel format: ")+
        GetPixelFormatName(static_cast<PfncFormat>(image.getPixelFormat())));
      break;
  }

  return full_name;
}

#ifdef INCLUDE_PNG

std::string storeImagePNG(const std::string &name, const rcg::Image &image, size_t yoffset,
  size_t height)
{
  size_t width=image.getWidth();
  size_t real_height=image.getHeight();

  if (height == 0) height=real_height;

  yoffset=std::min(yoffset, real_height);
  height=std::min(height, real_height-yoffset);

  const unsigned char *p=static_cast<const unsigned char *>(image.getPixels());

  size_t px=image.getXPadding();

  uint64_t format=image.getPixelFormat();
  std::string full_name;

  switch (format)
  {
    case Mono8: // store 8 bit monochrome image
    case Confidence8:
    case Error8:
      {
        // open file and init

        full_name=ensureNewFileName(name+".png");
        FILE *out=fopen(full_name.c_str(), "wb");

        if (!out)
        {
          throw new IOException("Cannot store file: "+ensureNewFileName(name+".pgm"));
        }

        png_structp png=png_create_write_struct(PNG_LIBPNG_VER_STRING, 0, 0, 0);
        png_infop info=png_create_info_struct(png);
        setjmp(png_jmpbuf(png));

        // write header

        png_init_io(png, out);
        png_set_IHDR(png, info, width, height, 8, PNG_COLOR_TYPE_GRAY,
          PNG_INTERLACE_NONE, PNG_COMPRESSION_TYPE_DEFAULT,
          PNG_FILTER_TYPE_DEFAULT);
        png_write_info(png, info);

        // write image body

        p+=(width+px)*yoffset;
        for (size_t k=0; k<height; k++)
        {
          png_write_row(png, const_cast<png_bytep>(p));
          p+=width+px;
        }

        // close file

        png_write_end(png, info);
        fclose(out);
        png_destroy_write_struct(&png, &info);
      }
      break;

    case Mono16:
    case Coord3D_C16: // store 16 bit monochrome image
      {
        // open file and init

        full_name=ensureNewFileName(name+".png");
        FILE *out=fopen(full_name.c_str(), "wb");

        if (!out)
        {
          throw new IOException("Cannot store file: "+full_name);
        }

        png_structp png=png_create_write_struct(PNG_LIBPNG_VER_STRING, 0, 0, 0);
        png_infop info=png_create_info_struct(png);
        setjmp(png_jmpbuf(png));

        // write header

        png_init_io(png, out);
        png_set_IHDR(png, info, width, height, 16, PNG_COLOR_TYPE_GRAY,
          PNG_INTERLACE_NONE, PNG_COMPRESSION_TYPE_DEFAULT,
          PNG_FILTER_TYPE_DEFAULT);
        png_write_info(png, info);

        // write image body

        if (!image.isBigEndian())
        {
          png_set_swap(png);
        }

        p+=(2*width+px)*yoffset;
        for (size_t k=0; k<height; k++)
        {
          png_write_row(png, const_cast<png_bytep>(p));
          p+=2*width+px;
        }

        // close file

        png_write_end(png, info);
        fclose(out);
        png_destroy_write_struct(&png, &info);
      }
      break;

    case YCbCr411_8: // convert and store as color image
      {
        // open file and init

        full_name=ensureNewFileName(name+".png");
        FILE *out=fopen(full_name.c_str(), "wb");

        if (!out)
        {
          throw new IOException("Cannot store file: "+full_name);
        }

        png_structp png=png_create_write_struct(PNG_LIBPNG_VER_STRING, 0, 0, 0);
        png_infop info=png_create_info_struct(png);
        setjmp(png_jmpbuf(png));

        // write header

        png_init_io(png, out);
        png_set_IHDR(png, info, width, height, 8, PNG_COLOR_TYPE_RGB,
          PNG_INTERLACE_NONE, PNG_COMPRESSION_TYPE_DEFAULT,
          PNG_FILTER_TYPE_DEFAULT);
        png_write_info(png, info);

        // write image body

        uint8_t *tmp=new uint8_t [3*width];

        size_t pstep=(width>>2)*6+px;

        p+=pstep*yoffset;
        for (size_t k=0; k<height; k++)
        {
          for (size_t i=0; i<width; i+=4)
          {
            rcg::convYCbCr411toQuadRGB(tmp+3*i, p, static_cast<int>(i));
          }

          png_write_row(png, tmp);
          p+=pstep;
        }

        // close file

        png_write_end(png, info);
        fclose(out);
        png_destroy_write_struct(&png, &info);
      }
      break;

    default:
      throw IOException(std::string("storeImage(): Unknown pixel format: ")+
        GetPixelFormatName(static_cast<PfncFormat>(image.getPixelFormat())));
      break;
  }

  return full_name;
}

#endif

}

std::string storeImage(const std::string &name, ImgFmt fmt, const rcg::Image &image,
  size_t yoffset, size_t height)
{
  std::string ret;

  switch (fmt)
  {
    case PNG:
#ifdef INCLUDE_PNG
      ret=storeImagePNG(name, image, yoffset, height);
#else
      throw IOException("storeImage(): Support for PNG image file format is not compiled in!");
#endif
      break;

    default:
    case PNM:
      ret=storeImagePNM(name, image, yoffset, height);
      break;
  }

  return ret;
}

std::string storeImageAsDisparityPFM(const std::string &name, const rcg::Image &image, int inv,
  float scale, float offset)
{
  if (image.getPixelFormat() != Coord3D_C16)
  {
    throw IOException(std::string("storeImageAsDisparityPFM(): Format Coord3D_C16 expected: ")+
      GetPixelFormatName(static_cast<PfncFormat>(image.getPixelFormat())));
  }

  if (scale == 0)
  {
    throw IOException(std::string("storeImageAsDisparityPFM(): Scale must not be 0!"));
  }

  // convert values and store disparity image

  size_t px=image.getXPadding();
  size_t width=image.getWidth();
  size_t height=image.getHeight();
  const unsigned char *p=static_cast<const unsigned char *>(image.getPixels())+
    2*(width+px)*(height+1);

  std::string full_name=ensureNewFileName(name+".pfm");
  std::ofstream out(full_name, std::ios::binary);

  out << "Pf" << std::endl;
  out << width << " " << height << std::endl;
  out << 1 << "\n";

  std::streambuf *sb=out.rdbuf();

  // get 16 bit data, scale and add offset and store as big endian

  bool msbfirst=true;

  {
    int pp=1;
    char *cc=reinterpret_cast<char *>(&pp);
    msbfirst=(cc[0] != 1);
  }

  for (size_t k=0; k<height && out.good(); k++)
  {
    p-=(width+px)<<2;
    for (size_t i=0; i<width; i++)
    {
      int val;
      if (image.isBigEndian())
      {
        val=(static_cast<int>(p[0])<<8)|p[1];
      }
      else
      {
        val=(static_cast<int>(p[1])<<8)|p[0];
      }

      p+=2;

      float d=std::numeric_limits<float>::infinity();
      if (val != inv)
      {
        d=static_cast<float>(val*scale+offset);
      }

      char *c=reinterpret_cast<char *>(&d);

      if (msbfirst)
      {
        sb->sputc(c[0]);
        sb->sputc(c[1]);
        sb->sputc(c[2]);
        sb->sputc(c[3]);
      }
      else
      {
        sb->sputc(c[3]);
        sb->sputc(c[2]);
        sb->sputc(c[1]);
        sb->sputc(c[0]);
      }

      p+=px;
    }
  }

  out.close();

  return full_name;
}

}
