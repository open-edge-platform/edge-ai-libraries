//***************************************************************************
//   (C) 2005 STEMMER IMAGING
//
///  \file
///     GenICam Common Error Values
///  \author    Rupert Stelz (STEMMER IMAGING)
///  \version   0.1
///  \date      2005
 /// \ingroup Base_PublicUtilities
//
//  License: This file is published under the license of the EMVA GenICam  Standard Group.
//  A text file describing the legal terms is included in  your installation as 'GenICam_license.pdf'.
//  If for some reason you are missing  this file please contact the EMVA or visit the website
//  (http://www.genicam.org) for a full copy.
//
//  THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
//  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
//  OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
//  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
//  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
//  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
//  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
//  ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
//  POSSIBILITY OF SUCH DAMAGE.
//***************************************************************************

// TLIClientDummy.dll GenICam TransportLayer Dummy Client

#ifndef GC_ERROR_DEF_H
#define GC_ERROR_DEF_H

#include <Base/GCTypes.h>

namespace GENICAM_NAMESPACE
{
  /// Gen Cam Error
  //! \ingroup Base_PublicUtilities
  typedef int32_t GC_ERROR;

  //! Define a list which maps error ids to error descriptions
  //! The list is filled in the cpp file
  //! \ingroup Base_PublicUtilities
  enum GCErrorID
  {
    GC_ERR_SUCCESS             = 0,
    GC_ERR_INVALID_BUFFER_SIZE = -1,
    GC_ERR_INVALID_HANDLE      = -2,
    GC_ERR_INVALID_ID          = -3,
    GC_ERR_ACCESS_DENIED       = -4,
    GC_ERR_NO_DATA             = -5,
    GC_ERR_ERROR               = -6,
    GC_ERR_INVALID_PARAMETER   = -7,
    GC_ERR_TIMEOUT             = -8,
    GC_ERR_INVALID_FILENAME    = -9,
    GC_ERR_INVALID_ADDRESS     = -10,
    GC_ERR_FILE_IO             = -11
  };

  //! Modules were errors can come from
  //! \ingroup Base_PublicUtilities
  enum GCModuleID {
    GC_MOD_SYSTEM     = 0x0,
    GC_MOD_TLICLIENT  = 0x20000000,
    GC_MOD_TLISYSTEM  = 0x10000000,
    GC_MOD_FACTORY    = 0x08000000,
    GC_MOD_GENAPI     = 0x04000000

  };

  #define GC_GET_ERROR(ErrorCode) (((ErrorCode ) & 0xFFFF ) | 0xFFFF0000)
  #define GC_IS_ERROR(ErrorCode)  (((ErrorCode ) & 0x80000000) ? true : false)
}
#endif //GC_ERROR_DEF_H
