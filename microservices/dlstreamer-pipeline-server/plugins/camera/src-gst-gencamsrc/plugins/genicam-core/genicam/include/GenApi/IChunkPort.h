//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Fritz Dierks
//  $Header$
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
//-----------------------------------------------------------------------------
/*!
\file
\brief    Definition of interface IChunkPort
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_ICHUNKPORT_H
#define GENAPI_ICHUNKPORT_H

#include <Base/GCBase.h>
#include <GenApi/GenApiDll.h>
#include <GenApi/Types.h>
#include <GenApi/IPort.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // IChunkPort interface
    //*************************************************************

    //! Address of a int64_t pseudo register containing the base address of the chunk (MAX_INT64)
#   define CHUNK_BASE_ADDRESS_REGISTER     GC_INT64_MAX

    //! Length of the CHUNK_BASE_ADDRESS_REGISTER pseudo register
#   define CHUNK_BASE_ADDRESS_REGISTER_LEN 8

    //! Address of a int64_t pseudo register containing the length of the chunk
#   define CHUNK_LENGTH_REGISTER     (GC_INT64_MAX-15)

    //! Length of the CHUNK_LENGTH_REGISTER pseudo register
#   define CHUNK_LENGTH_REGISTER_LEN 8

    /**
    \brief Interface for ports attached to a chunk
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IChunkPort : virtual public IPort
    {
        //! Get the Id of the chunk the port should be attached to
        virtual GENICAM_NAMESPACE::gcstring GetChunkID() const =  0;

        //! Indicates if the chunk a adapter must hold a cached version of the chunk data
        virtual EYesNo CacheChunkData() const =  0;
    };
}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_ICHUNKPORT_H
