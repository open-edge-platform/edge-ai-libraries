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
\brief    Declaration of the CChunkAdapter class.
\ingroup GenApi_PublicUtilities
*/

#ifndef GENAPI_CHUNKADAPTER_H
#define GENAPI_CHUNKADAPTER_H

#include <GenApi/Types.h>
#include <GenApi/INodeMap.h>
#include <GenApi/ChunkPort.h>
#include <vector>

namespace GENAPI_NAMESPACE
{


    //! Delivers information about the attached chunks and nodes
    //! \ingroup GenApi_PublicUtilities
    typedef struct AttachStatistics_t
    {
        int NumChunkPorts;        //!< Number of chunk ports found in the node map
        int NumChunks;            //!< Number of chunks found in the buffer
        int NumAttachedChunks;    //!< Number of chunks from the buffer attached to a chunk port
    } AttachStatistics_t;


    /**
    \brief Connects a chunked buffer to a node map
    \ingroup GenApi_PublicUtilities
    */
    class GENAPI_DECL CChunkAdapter
    {

    public:
        //! Destructor
        virtual ~CChunkAdapter();

        //! Attaches to a node map and retrieves the chunk ports
        void AttachNodeMap(INodeMap* pNodeMap);

        //! Detaches from the node map
        void DetachNodeMap();

        //! Checks if a buffer contains chunks in a known format
        /*! Implement that for a specific buffer layout */
        virtual bool CheckBufferLayout(uint8_t *pBuffer, int64_t BufferLength) = 0;

        //! Attaches a buffer to the matching ChunkPort
        /*! Implement that for a specific buffer layout */
        virtual void AttachBuffer(uint8_t *pBuffer, int64_t BufferLength, AttachStatistics_t *pAttachStatistics = NULL) = 0;

        //! Detaches a buffer
        void DetachBuffer();

        //! Updates the base address of the buffer
        void UpdateBuffer(uint8_t *pBaseAddress);

        //! Clears the chunk caches
        void ClearCaches();

    protected:

        //! Serves as default constructor
        CChunkAdapter(INodeMap* pNodeMap = NULL, int64_t MaxChunkCacheSize = -1);

        //! An array of attached ChunkPorts
        /*! Note that this must be a pointer otherwise we'll get into DLL hell (see warning C4251) */
        std::vector<CChunkPort*> *m_ppChunkPorts;

        //! the maximum size of a chunk to be cached
        /*! 0 : no caching, -1 : all caching */
        int64_t m_MaxChunkCacheSize;

    };

}

#endif // GENAPI_CHUNKADAPTER_H
