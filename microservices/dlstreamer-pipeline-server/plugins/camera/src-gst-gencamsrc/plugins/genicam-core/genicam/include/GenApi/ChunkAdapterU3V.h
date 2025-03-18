//-----------------------------------------------------------------------------
//  (c) 2013 by Groget
//  Project:  GenApi
//    Author:  Jan Becvar
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
/**
\file
\brief    Declaration of the CChunkAdapterU3V class.
*/

#ifndef GENAPI_CHUNKADAPTERU3V_H
#define GENAPI_CHUNKADAPTERU3V_H

#include <GenApi/ChunkAdapter.h>

namespace GENAPI_NAMESPACE
{

    /* ------------------------------------------- */
    // Declartion of USB3 Vision Chunk trailer

    // make sure everything is properly packed
#   pragma pack(push, 1)

    //! header of a GVCP request packet
    typedef struct U3V_CHUNK_TRAILER
    {
        uint32_t ChunkID;
        uint32_t ChunkLength;
    } U3V_CHUNK_TRAILER;

    // restore the previous packing
#   pragma pack(pop)
    /* ------------------------------------------- */


    //! Connects a chunked U3V buffer to a node map
    class GENAPI_DECL CChunkAdapterU3V : public  CChunkAdapter
    {

    public:
        //! Constructor
        CChunkAdapterU3V(INodeMap* pNodeMap = NULL, int64_t MaxChunkCacheSize = -1);

        //! Destructor
        virtual ~CChunkAdapterU3V();

        //! Checks if a buffer contains chunks in a known format
        virtual bool CheckBufferLayout(uint8_t *pBuffer, int64_t BufferLength);

        //! Attaches a buffer to the matching ChunkPort
        virtual void AttachBuffer(uint8_t *pBuffer, int64_t BufferLength, AttachStatistics_t *pAttachStatistics = NULL);

    };

}

#endif // GENAPI_CHUNKADAPTERU3V_H
