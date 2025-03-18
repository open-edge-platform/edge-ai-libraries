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
\brief    Definition of CPort
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_PORT_H
#define GENAPI_PORT_H

#include "../Types.h"
#include "../IPortConstruct.h"
#include "../IChunkPort.h"
#include "../IPortRecorder.h"
#include "../IString.h"
#include "Node.h"
#include "NodeT.h"
#include "BaseT.h"

namespace GENAPI_NAMESPACE
{

    class CValueCache;

    //*************************************************************
    // CPort class
    //*************************************************************

    //! Standard IPort implementation
    /*! Proxy forwarding all calls to the real implementation
    */
    class CPortImplIntern :
        public IPortConstruct,
        public IChunkPort,
        public IPortRecorder,
        public CNodeImpl
    {
    public:
        //! Default constructor
        //constructor
        CPortImplIntern();

        //! Destructor
        virtual ~CPortImplIntern();

        //-------------------------------------------------------------
        // IBase implementation
        //-------------------------------------------------------------

    protected:
        //! Get the access mode of the node
        virtual EAccessMode InternalGetAccessMode() const;

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIPort;
        }

        //-------------------------------------------------------------
        // IPort implementation
        //-------------------------------------------------------------

    public:
        //! Reads a chunk of bytes from the port
        virtual void Read(void *pBuffer, int64_t Address, int64_t Length);

        //! Writes a chunk of bytes to the port
        virtual void Write(const void *pBuffer, int64_t Address, int64_t Length);

        //-------------------------------------------------------------
        // IPortConstruct implementation
        //-------------------------------------------------------------

        //! Sets pointer the real port implementation; this function may called only once
        void SetPortImpl(IPort* pPort);

        //-------------------------------------------------------------
        // IChunkPort implementation
        //-------------------------------------------------------------

        //! Get the Id of the chunk the port should be attached to
        virtual GENICAM_NAMESPACE::gcstring GetChunkID() const;

        //! Determines if the port adapter must perform an endianess swap
        virtual EYesNo GetSwapEndianess();

        //! Indicates if the chunk a adapter must hold a cached version of the chunk data
        virtual EYesNo CacheChunkData() const;

        //-------------------------------------------------------------
        // IPortRecorder implementation
        //-------------------------------------------------------------

        //! Starts logging all WriteRegister commands to a list
        virtual void StartRecording( IPortWriteList *pPortRecorder );

        //! Stops recording
        virtual void StopRecording();

        //-------------------------------------------------------------
        // IPortReplay implementation
        //-------------------------------------------------------------

        //! Sends the commands to the camera.
        /*! The default implementation just walks the list and issues each command
            using the WriteRegister method. Depending on the capabilities of
            the transport layer the implementation can however use a special command
            which sends all register write commands as one package.
        */
        virtual void Replay( IPortWriteList *pPortRecorder, bool Invalidate = true );

        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------
        
        
        virtual void SetProperty(CProperty &Property);
        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
        
        //! Returns the value cache
        virtual CValueCache* GetValueCache() const;


    protected:
        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------

        //! Pointer to node giving access to the real port implementation
        IPort *m_pPort;

        //! Pointer to node giving access to the real port implementation
        IPortWriteList *m_pPortWriteList;

        //! The ChunkID
        CStringPolyRef m_ChunkID;

        //! Pointer the value cache
        mutable GENAPI_NAMESPACE::CValueCache *m_pValueCache;

        //! Determines if the port adapter must perform an endianess swap
        EYesNo m_SwapEndianess;

        //! Determines if the port adapter must cache the chunk data
        EYesNo m_CacheChunkData;
    };

    class CPort : public BaseT<  NodeT< CPortImplIntern > >
    {
    };

}

#endif // ifndef GENAPI_PORT_H
