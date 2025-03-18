//-----------------------------------------------------------------------------
//  (c) 2006-8 by Basler Vision Technologies
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
\brief    Declaration of the CChunkPort class.
\ingroup GenApi_PublicUtilities
*/

#ifndef GENAPI_CHUNKPORT_H
#define GENAPI_CHUNKPORT_H

#include <GenApi/Pointer.h>
#include <GenApi/IPortConstruct.h>
#include <GenApi/INodeMap.h>

#ifdef _MSC_VER
#   pragma warning(push)
#   pragma warning(disable: 4251) // GenApi::CChunkPort::m_ptrPort' : class 'GenApi::CPointer<T>' needs to have dll-interface
#endif

namespace GENAPI_NAMESPACE
{

    /**
    \brief Port attachable to a chunk in a buffer
    \ingroup GenApi_PublicUtilities
    */
    class GENAPI_DECL CChunkPort : public IPortConstruct
    {

    public:

        //! Constructor; can attach to a port
        CChunkPort(IPort* pPort = NULL);

        //! Destructor; detaches from the port
        virtual ~CChunkPort();

        //-------------------------------------------------------------
        // IPortConstruct implementation
        //-------------------------------------------------------------

        //! Get the access mode of the node
        virtual EAccessMode GetAccessMode() const;

        //! Get the type of the main interface of a node
        virtual EInterfaceType GetPrincipalInterfaceType() const;

        //! Reads a chunk of bytes from the port
        virtual void Read(void *pBuffer, int64_t Address, int64_t Length);

        //! Writes a chunk of bytes to the port
        virtual void Write(const void *pBuffer, int64_t Address, int64_t Length);

        //! Called from the port node to give the chunk port a pointer to itself
        virtual void SetPortImpl(GENAPI_NAMESPACE::IPort* pPort);

        //! Determines if the port adapter must perform an endianess swap
        virtual EYesNo GetSwapEndianess()
        {
            return No;
        }

        //---------------------------------------------------------------
        // Implementation
        //---------------------------------------------------------------

        // Invalidates the chunk port node
        void InvalidateNode();

        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------

        //! Attaches the ChunkPort to the Port
        bool AttachPort(GENAPI_NAMESPACE::IPort* pPort);

        //! Detaches the ChunkPort to the Port
        void DetachPort();

        //! Attaches the Chunk to the ChunkPort
        void AttachChunk(uint8_t *pBaseAddress, int64_t ChunkOffset, int64_t Length, bool Cache);

        //! Detaches the Chunk from the ChunkPort
        void DetachChunk();

        //! Gets the ChunkID length
        int GetChunkIDLength()
        {
            return m_ChunkIDLength;
        }

        //! Checks if a ChunkID matches
        bool CheckChunkID(uint8_t* pChunkIDBuffer, int ChunkIDLength);

        //! Checks if a ChunkID matches, version using uint64_t ID representation
        bool CheckChunkID(uint64_t ChunkID);

        //! Updates the base address of the chunk
        void UpdateBuffer(uint8_t *pBaseAddress);

        //! Clears the chunk cache
        void ClearCache();
    protected:

        CLock& GetLock() const
        {
            if (!m_ptrPort.IsValid())
                throw RUNTIME_EXCEPTION("The event port is not attached to a node");

            return m_ptrPort->GetNodeMap()->GetLock();
        }

        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------

        //! Pointer to the begin of the buffer
        uint8_t *m_pBaseAddress;

        //! The chunk's offset within the buffer
        int64_t m_ChunkOffset;

        //! Length of the chunk
        int64_t m_Length;

        //! Space allocated for the chunk
        int64_t m_LengthAlloc;

        //! Pointer to the node holding a reference to this implementation
        CNodePtr m_ptrPort;

        //! Binary version of the chunk ID
        uint8_t *m_pChunkIDBuffer;

        //! Length of the chunk ID buffer
        int m_ChunkIDLength;

        //! cache for the chunk data
        uint8_t *m_pChunkData;

        //! indicates if the data needs to be cached
        bool m_CacheData;

        //! Chunk ID stored as a number (for more straightforward access)
        uint64_t m_ChunkIDNumber;

        //! indicates if the m_ChunkIDNumber is valid (could be invalid eg. if the ID does not fit in 64-bit range)
        bool m_ChunkIDNumberValid;
     };

}

#ifdef _MSC_VER
#   pragma warning(pop)
#endif

#endif // GENAPI_CHUNKPORT_H
