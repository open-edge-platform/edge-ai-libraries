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
\brief    Declaration of the CEventPort class.
\ingroup GenApi_PublicUtilities
*/

#ifndef GENAPI_EVENTPORT_H
#define GENAPI_EVENTPORT_H

#include <GenApi/Pointer.h>
#include <GenApi/IPortConstruct.h>
#include <GenApi/INodeMap.h>

namespace GENAPI_NAMESPACE
{

    /**
    \brief Port attachable to an event
    \ingroup GenApi_PublicUtilities
    */
    class GENAPI_DECL CEventPort : public IPortConstruct
    {

    public:
        //! Constructor; can attach to a node
        CEventPort(INode* pNode = NULL);

        //! Destructor; detaches from the port
        ~CEventPort();

        //-------------------------------------------------------------
        // IPortConstruct implementation
        //-------------------------------------------------------------

        //!    Get    the    access mode    of the node
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
        virtual EYesNo GetSwapEndianess();

        //---------------------------------------------------------------
        // Implementation
        //---------------------------------------------------------------

        // Invalidates the chunk port node
        void InvalidateNode();

        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------

        //! Attaches to the Node
        bool AttachNode(GENAPI_NAMESPACE::INode* pNode);

        //! Detaches from the Node
        void DetachNode();

        //! Gets the EventID length
        int GetEventIDLength();

        //! Checks if a EventID matches
        bool CheckEventID(uint8_t* pEventIDBuffer, int EventIDLength) const;

        //! Checks if a EventID matches, version using uint64_t ID representation
        bool CheckEventID(uint64_t EventID) const;

        //! Attaches the an Event to the EventPort
        void AttachEvent(uint8_t *pBaseAddress, int64_t Length);

        //! Detaches the Event from the EventPort
        void DetachEvent();

    protected:

        CLock& GetLock() const;
    private:
        void ResetEventDataBuffer();

        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------

        //! Pointer to the begin of the buffer
        uint8_t *m_pEventData;

        //! Length of the data
        int64_t m_EventDataLength;

        //! Space allocated for the data
        int64_t m_EventDataAlloc;
#ifdef _MSC_VER
#   pragma warning( push )
#   pragma warning( disable: 4251 )
#endif
        //! Pointer to the node holding a reference to this implementation
        CNodePtr m_ptrNode;
#ifdef _MSC_VER
#   pragma warning( pop )
#endif

        //! Binary version of the EventID
        uint8_t *m_pEventIDBuffer;

        //! Length of the EventID buffer
        int m_EventIDLength;

        //! indicates if the object is attached to a port node or another node type
        bool m_IsAttachedToPortNode;

        //! Event ID stored as a number (for more straightforward access)
        uint64_t m_EventIDNumber;

        //! indicates if the m_EventIDNumber is valid (could be invalid eg. if the ID does not fit in 64-bit range)
        bool m_EventIDNumberValid;
    };

}
#endif // GENAPI_EVENTPORT_H
