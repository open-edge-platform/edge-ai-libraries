//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section:  Vision Components
//  Project:  GenApi
//    Author:  Fritz Dierks
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
\brief    Declaration of the CChunkAdapterGEV class.
*/

#ifndef GENAPI_CHUNKADAPTERGEV_H
#define GENAPI_CHUNKADAPTERGEV_H

#include <GenApi/ChunkAdapter.h>

namespace GENAPI_NAMESPACE
{

    /* ------------------------------------------- */
    // Declartion of GigE Vision Chunk message trailer

    // make sure everything is properly packed
#   pragma pack(push, 1)

    //! header of a GVCP request packet
    typedef struct GVCP_CHUNK_TRAILER
    {
        uint32_t ChunkID;
        uint32_t ChunkLength;
    } GVCP_CHUNK_TRAILER;

    // restore the previous packing
#   pragma pack(pop)
    /* ------------------------------------------- */


    //! Connects a chunked DCAM buffer to a node map
    class GENAPI_DECL CChunkAdapterGEV : public  CChunkAdapter
    {

    public:
        //! Constructor
        CChunkAdapterGEV(INodeMap* pNodeMap = NULL, int64_t MaxChunkCacheSize = -1);

        //! Destructor
        virtual ~CChunkAdapterGEV();

        //! Checks if a buffer contains chunks in a known format
        virtual bool CheckBufferLayout(uint8_t *pBuffer, int64_t BufferLength);

        //! Attaches a buffer to the matching ChunkPort
        virtual void AttachBuffer(uint8_t *pBuffer, int64_t BufferLength, AttachStatistics_t *pAttachStatistics = NULL);

    };

}

#endif // GENAPI_CHUNKADAPTERGEV_H
