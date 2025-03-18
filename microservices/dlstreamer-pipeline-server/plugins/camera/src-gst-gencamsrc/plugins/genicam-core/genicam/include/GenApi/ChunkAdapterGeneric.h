//-----------------------------------------------------------------------------
//  (c) 2006 by Leutron Vision
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
\brief    Declaration of the CChunkAdapterGeneric class.
*/

#ifndef GENAPI_CHUNKADAPTERGENERIC_H
#define GENAPI_CHUNKADAPTERGENERIC_H

#include <GenApi/ChunkAdapter.h>

namespace GENAPI_NAMESPACE
{
    /* ------------------------------------------- */
    // Single chunk info

    // make sure everything is properly packed
    #pragma pack(push, 1)

    typedef struct SingleChunkData_t
    {
        uint64_t ChunkID;
        ptrdiff_t ChunkOffset;
        size_t ChunkLength;
    } SingleChunkData_t;

    // the extended version holding ChunkID as string should be used only in special cases
    // when the ChunkID does not fit into a 64-bit integer
    typedef struct SingleChunkDataStr_t
    {
        GENICAM_NAMESPACE::gcstring ChunkID;
        ptrdiff_t ChunkOffset;
        size_t ChunkLength;
    } SingleChunkDataStr_t;

    // restore the previous packing
    #pragma pack(pop)
    /* ------------------------------------------- */


    //! Connects a generic chunked buffer to a node map
    class GENAPI_DECL CChunkAdapterGeneric : public CChunkAdapter
    {

    public:
        //! Constructor
        CChunkAdapterGeneric(INodeMap* pNodeMap = NULL, int64_t MaxChunkCacheSize = -1);

        //! Destructor
        virtual ~CChunkAdapterGeneric();

        // Does not have implementation, use the version with EventID
        virtual bool CheckBufferLayout(uint8_t *pBuffer, int64_t BufferLength);

        // Does not have implementation, use the generic version
        virtual void AttachBuffer(uint8_t *pBuffer, int64_t BufferLength, AttachStatistics_t *pAttachStatistics = NULL);

        virtual void AttachBuffer(uint8_t *pBuffer, SingleChunkData_t *ChunkData, int64_t NumChunks, AttachStatistics_t *pAttachStatistics = NULL);

        virtual void AttachBuffer(uint8_t *pBuffer, SingleChunkDataStr_t *ChunkData, int64_t NumChunks, AttachStatistics_t *pAttachStatistics = NULL);
    };

}

#endif // GENAPI_CHUNKADAPTERGENERIC_H
