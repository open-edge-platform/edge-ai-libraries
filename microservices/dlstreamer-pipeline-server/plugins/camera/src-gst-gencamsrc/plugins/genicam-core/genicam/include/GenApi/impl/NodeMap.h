//-----------------------------------------------------------------------------
//  (c) 2006 by Basler 
//  Project: GenApi
//  Author:  Fritz Dierks
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
\brief    Declaration of CNodeMap 
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_NODEMAP_H
#define GENAPI_NODEMAP_H

#include "GenApi/GenApiVersion.h"
#include "GenApi/GenApiDll.h"
#include "GenApi/impl/INodeMapPrivate.h"
#include "GenApi/impl/INodePrivate.h"
#include "GenApi/IDestroy.h"
#include "GenApi/IDeviceInfo.h"
#include "GenApi/Synch.h"
#include "Base/GCString.h"
#include "GenApi/impl/Value2String.h"
#include "GenApi/IUserData.h"
#include <map>

#ifdef _MSC_VER 
#	pragma warning(push)
#	pragma warning(disable: 4251) // class 'xxx' needs to have dll-interface to be used by clients of class 'yyy'
#endif

namespace GENAPI_NAMESPACE
{

    typedef  INodePrivate*(*CreateFunc_t)( const GENICAM_NAMESPACE::gcstring& );

    class string2node_t;
    /**
    \brief Hold a map of all nodes
    */
    class CNodeMap
        : virtual public INodeMapPrivate
        , public IDeviceInfo
        , public IDestroy
        , public IUserData
    {
    public:
        //----------------------------------------------------------------
        // Construction 
        //----------------------------------------------------------------

        //! Constructor
        CNodeMap(const GENICAM_NAMESPACE::gcstring& DeviceName = "Device", CLock* pUserProvidedLock = NULL);

        //-------------------------------------------------------------
        //! \name Interface INodeMap 
        //@{
            virtual void GetNodes(NodeList_t &Nodes) const;
            virtual INode* GetNode(const GENICAM_NAMESPACE::gcstring& Name) const;
            virtual void InvalidateNodes() const;
            virtual bool Connect(IPort* pPort, const GENICAM_NAMESPACE::gcstring& PortName) const;
            virtual bool Connect(IPort* pPort) const;
            virtual GENICAM_NAMESPACE::gcstring GetDeviceName();
            virtual void Poll(int64_t ElapsedTime);
            virtual CLock& GetLock() const;
            virtual uint64_t GetNumNodes() const;
            virtual bool ParseSwissKnifes( GENICAM_NAMESPACE::gcstring_vector *pErrorList = NULL ) const;
        //@}

        //-------------------------------------------------------------
        //! \name Interface INodeMapPrivate 
        //@{
            virtual void RegisterNode(INodePrivate* pNode, CNodeData::ENodeType_t NodeType, NodeID_t NodeID);
            virtual void FinalConstruct(bool DetermineDependencies);
            virtual void SetNumNodes(size_t NumNodes);
            virtual INodePrivate* GetNodeByID(NodeID_t NodeID);
            virtual void SetProperty(CProperty &Property);
            virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
            virtual Counter& GetBathometer() { return m_Bathometer; }
            virtual void SetEntryPoint(EMethod EntryMethod, const INodePrivate *pEntryNode, bool IgnoreCache);
            virtual void ResetEntryPoint();
            virtual GENICAM_NAMESPACE::gcstring GetEntryPoint();
            virtual bool IsGenApiLoggingEnabled();
            virtual bool IsGenApiDeviceLoggingEnabled();
            //@}

        //-------------------------------------------------------------
        //! \name Interface IDeviceInfo
        //@{
            virtual GENICAM_NAMESPACE::gcstring GetModelName();
            virtual GENICAM_NAMESPACE::gcstring GetVendorName();
            virtual GENICAM_NAMESPACE::gcstring GetToolTip();
            virtual GENICAM_NAMESPACE::gcstring GetStandardNameSpace();
            virtual void GetGenApiVersion(Version_t &Version, uint16_t &Build);
            virtual void GetSchemaVersion(Version_t &Version);
            virtual void GetDeviceVersion(Version_t &Version);
            virtual GENICAM_NAMESPACE::gcstring GetProductGuid();
            virtual GENICAM_NAMESPACE::gcstring GetVersionGuid();
        //@}
    private:
        //-------------------------------------------------------------
        //! \name Interface IUserData
        //@{
        virtual UserData_t GetUserData() const;
        virtual UserData_t SetUserData( UserData_t userdata );
        //@}
    public:
        //-------------------------------------------------------------
        //! \name Interface IDestroy 
        //! Makes the object to destroy itself
        virtual void Destroy();
        //@}

        // Fast Track...
        inline INodePrivate* _GetNodeByID( NodeID_t NodeID )
        {
            assert((size_t)NodeID.ToIndex() < m_Node2NodeID.size());
            return m_Node2NodeID[(size_t)NodeID.ToIndex()];
        }

    protected:
        //-------------------------------------------------------------
        // DeviceInfo members
        //-------------------------------------------------------------

        //! model name
        GENICAM_NAMESPACE::gcstring m_ModelName;

        //! Get the vendor name
        GENICAM_NAMESPACE::gcstring m_VendorName;

        //! tool tip
        GENICAM_NAMESPACE::gcstring m_ToolTip;

        //! standard name space
        GENAPI_NAMESPACE::EStandardNameSpace m_StandardNameSpace;

        //! schema version number
        Version_t m_SchemaVersion;

        //! device description file's version number
        Version_t m_DeviceVersion;

        //! Guid describing the product
        GENICAM_NAMESPACE::gcstring m_ProductGuid;

        //! Guid describing the product version
        GENICAM_NAMESPACE::gcstring m_VersionGuid;

        //! A list with all properties set
        GENICAM_NAMESPACE::gcstring_vector m_PropertyNames;

        //! The name of the device
        GENICAM_NAMESPACE::gcstring m_DeviceName;

        //! Dummy name, used only for loading
        GENICAM_NAMESPACE::gcstring m_Name;

        //-------------------------------------------------------------
        // Node containers
        //-------------------------------------------------------------

        //! Holds the Node pointers referenced by NodeID
        typedef std::vector<INodePrivate*> Node2NodeID_t;
        Node2NodeID_t m_Node2NodeID;

        //! Holds the Node pointers referenced by NodeName
        string2node_t *m_pMap;

        //! Retrieve the map
        string2node_t& Map();

        //! Retrieve the map
        const string2node_t& Map() const;

        //-------------------------------------------------------------
        // Destruction
        //-------------------------------------------------------------

        //! Destructor (note that in order to destroy the node map you need to call IDestroy::Destroy()
        virtual ~CNodeMap();

        //! Clear the map
        void ClearAllNodes();

        //-------------------------------------------------------------
        // Call-stack implementation 
        //-------------------------------------------------------------

        //! counts the depth of SetValue call-chains
        Counter m_Bathometer;

        //! The node where a call entered the tree
        const INodePrivate *m_pEntryNode;

        //! The node where a call entered the tree
        EMethod m_EntryMethod;

        //! Number of call pairs to SetEntryPoint/ResetEntryPoint
        int m_EntryPointDepth;

        //! Indicates if the entry point had the Ignore Cache flag set
        bool m_EntryPointIgnoreCache;

        //! List of pointers to nodes which need to be polled
        NodePrivateVector_t* m_pPollingNodes;

        //! indicates GenApi logging is enabled (caches the returnvalue of CLog::Exists("GenApi") )
        bool m_GenApiLoggingEnabled;

        //! indicates GenApi logging is enabled (caches the returnvalue of CLog::Exists("GenApi.Device") )
        bool m_GenApiDeviceLoggingEnabled;

    private:
        //! The own lock guarding access to the node map
        //! Do not use this directly! Use GetLock() instead
        CLock m_zzz_OwnLock_DoNotUse;
    private:
        //! Storage of user defined data.
        //! Ownership remains by the user!. Use IUserData interface to access the data.
        UserData_t m_pUserData;

    protected:
        //! The pointer to the lock guarding access to the node map
        //! This may be changed by the user if he decides to use another lock
        CLock& m_Lock;


        //-------------------------------------------------------------
        // No copying of this class
        //-------------------------------------------------------------
    private:
        //! forbidden copy constructor
        CNodeMap(const CNodeMap&);

        //! forbidden operator=
        CNodeMap& operator=(const CNodeMap&);

    };
}

#ifdef _MSC_VER 
#	pragma warning(pop)
#endif

#endif // GENAPI_NODEMAP_H
