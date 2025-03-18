//-----------------------------------------------------------------------------
//  (c) 2006-2009 by Basler Vision Technologies
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
    \ingroup GenApi_Implementation
*/

#ifndef GENAPI_NODE_H
#define GENAPI_NODE_H

#include <string>
#include <sstream>
#include <algorithm>
#include <cctype>
#include "Base/GCException.h"
#include "../GenApiDll.h"
#include "../Synch.h"
#include "../Types.h"
#include "../INode.h"
#include "../ICategory.h"
#include "INodePrivate.h"
#include "INodeMapPrivate.h"
#include "../IInteger.h"
#include "../IBoolean.h"
#include "../ISelector.h"
#include "../NodeCallback.h"
#include "../EnumClasses.h"
#include "Log.h"
#include "Value2String.h"
#include "PolyReference.h"
#include "NodeMapData/NodeMapDataTypes.h"
#include "NodeMapData/NodeData.h"
#include "NodeMap.h"
#include "../IUserData.h"
#include <list>

class CProperty;
class CNodeDataMap;

namespace GENAPI_NAMESPACE
{
    namespace detail
    {
        //! Add a value to container if not already present.
        template< typename C, typename V>
        void push_back_unique(C &c, const V &v)
        {
            if (std::find(c.begin(), c.end(), v) == c.end())
            {
                c.push_back(v);
            }
        }
    }

    //*************************************************************
    // CNodeImpl class
    //*************************************************************

    /*!
        \brief Standard implementation for the INode and the ISelector interface
        \ingroup GenApi_Implementation
    */
    class CNodeImpl : public INodePrivate, public ISelector, public IUserData
    {
    public:
        //-------------------------------------------------------------
        //! \name Constructor / destructor
        //@{
            //! Constructor
            CNodeImpl();

            //! Destructor
            virtual ~CNodeImpl();
        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Interface IBase (methods are called by the BaseT class)
        //@{
            //! Get the access mode of the node
            virtual EAccessMode InternalGetAccessMode() const;

            //! Implementation of IBase::GetPrincipalInterfaceType()
            #pragma BullseyeCoverage off
            virtual EInterfaceType InternalGetPrincipalInterfaceType() const
            {
                return intfIBase;
            }
            #pragma BullseyeCoverage on

            //! Default implementation of GetAccessMode taking into account another node
            EAccessMode InternalGetAccessMode(IBase* pValue) const;
        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Interface INode (methods are called by the NodeT class)
        //@{
            //! Get node name
            virtual GENICAM_NAMESPACE::gcstring InternalGetName(bool FullQualified=false) const;

            //! Get name space
            virtual GENAPI_NAMESPACE::ENameSpace InternalGetNameSpace()const;

            //! Get the recommended visibility of the node
            virtual EVisibility InternalGetVisibility() const;

            // Invalidate the node
            virtual void InternalInvalidateNode( std::list<CNodeCallback*> &CallbacksToFire );

            //! Is the node value cachable
            virtual bool InternalIsCachable() const;

            //! Get Caching Mode
            virtual ECachingMode InternalGetCachingMode() const;

            //! recommended polling time (for not cachable nodes)
            virtual int64_t InternalGetPollingTime() const;

            //! Get a short description of the node
            virtual GENICAM_NAMESPACE::gcstring InternalGetToolTip() const;

            //! Get a long description of the node
            virtual GENICAM_NAMESPACE::gcstring InternalGetDescription() const;

            // Get node display name
            virtual GENICAM_NAMESPACE::gcstring InternalGetDisplayName() const;

            //! Get a name of the device
            virtual GENICAM_NAMESPACE::gcstring InternalGetDeviceName() const;

            //! Get all children of the node
            virtual void InternalGetChildren(GENAPI_NAMESPACE::NodeList_t &Children, ELinkType LinkType) const;

            //! Register change callback
            /*! Takes ownership of the CNodeCallback object */
            virtual CallbackHandleType InternalRegisterCallback( CNodeCallback *pCallback );

            //! Deregister change callback
            /*! Destroys CNodeCallback object
                \return true if the callback handle was valid
            */
            virtual bool InternalDeregisterCallback( CallbackHandleType hCallback );

            //! Retrieves the node map
            virtual INodeMap* InternalGetNodeMap() const;

            //! Get the EventId of the node
            virtual GENICAM_NAMESPACE::gcstring GetEventID() const;

            //! True if the node is streamable
            virtual bool IsStreamable() const;

            virtual void GetParents(GENAPI_NAMESPACE::NodeList_t &Parents) const;

            //! Returns a list of the names all properties set during initialization
            virtual void GetPropertyNames(GENICAM_NAMESPACE::gcstring_vector &PropertyNames) const;

            //! Retrieves a property plus an additional attribute by name
            /*! If a property has multiple values/attribute they come with Tabs as delimiters */
            virtual bool GetProperty(const GENICAM_NAMESPACE::gcstring& PropertyName, GENICAM_NAMESPACE::gcstring& ValueStr, GENICAM_NAMESPACE::gcstring& AttributeStr) const;

            //! Imposes an access mode to the natural access mode of the node
            virtual void ImposeAccessMode(EAccessMode ImposedAccessMode);

            //! Imposes a visibility  to the natural visibility of the node
            virtual void ImposeVisibility(EVisibility ImposedVisibility);

            //! Retrieves the a node which describes the same feature in a different way
            virtual INode* GetAlias() const;

            //! Retrieves the a node which describes the same feature so that it can be casted
            virtual INode* GetCastAlias() const;

            //! Checks for an explicitly via the <pError> element defined error
            virtual void InternalCheckError() const;

            //! Gets a URL pointing to the documentation of that feature
            virtual GENICAM_NAMESPACE::gcstring InternalGetDocuURL() const;

            //! True if the node should not be used any more
            virtual bool InternalIsDeprecated() const;

            //! True if the node can be reached via category nodes from a category node named "Std::Root"
            virtual bool IsFeature() const;

            //! True if the AccessMode can be cached
            virtual EYesNo InternalIsAccessModeCacheable() const;

            //! returns true, if the AccessModeCache is valid
            /*! Handles silently the cycle breaker */
            inline bool IsAccessModeCached() const
            {
                if( _UndefinedAccesMode == m_AccessModeCache )
                    return false;
#pragma BullseyeCoverage off
                if( _CycleDetectAccesMode == m_AccessModeCache )
#pragma BullseyeCoverage on
                {
                    // the cycle is neutralized by making at least one node AccessMode cacheable
                    m_AccessModeCache = RW;
                    GCLOGWARN( m_pAccessLog,  "InternalGetAccessMode : ReadCycle detected at = '%s'", m_Name.c_str() );
                }
                return true;
            }
        //@}

    public:
        //-------------------------------------------------------------
        //! \name Interface INodePrivate
        //@{
            virtual void Initialize(GENAPI_NAMESPACE::INodeMapPrivate* const pNodeMap, CNodeData::ENodeType_t NodeType, NodeID_t &NodeID );
            virtual CNodeData::ENodeType_t GetNodeType();
            virtual NodeID_t GetNodeID();
            virtual void FinalConstruct();
            virtual void SetProperty( CProperty &Property );
            virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
            virtual void SetInvalid(ESetInvalidMode simMode);           
            virtual void CollectCallbacksToFire(std::list<CNodeCallback*> &CallbacksToFire, bool allDependents = false);
            virtual bool IsTerminalNode() const;
            virtual void GetTerminalNodes( GENAPI_NAMESPACE::NodeList_t& Terminals ) const;
            virtual bool Poll( int64_t ElapsedTime );
        //@}

    public:
        //-------------------------------------------------------------
        //! \name Interface ISelector
        //@{
            virtual bool IsSelector() const;
            virtual void GetSelectedFeatures( FeatureList_t& list ) const;
            virtual void GetSelectingFeatures( FeatureList_t& ) const;
        //@}

    public:

        //! Retrieves the INodeMapPrivate interface
        inline INodeMapPrivate* GetNodeMapPrivate()
        {
            return m_pNodeMap;
        }

        //! Sets a parent : CAVE : for internal use only...
        inline void SetParent( INodePrivate *pParent )
        {
            detail::push_back_unique(m_Parents, pParent);
        }

        // 1 : use macro for speed
        // 0 : used function for debugging
#if 0

#	define ADD_ORPHAN_CHILD( PropertyID, Property ) \
        INodePrivate *pNode = dynamic_cast<CNodeMap*>(m_pNodeMap)->_GetNodeByID( Property.NodeID() ); \
        if( CPropertyID::IsInvalidatingPointer(PropertyID) )\
        { \
            detail::push_back_unique(m_InvalidatingChildren, pNode); \
            if( CPropertyID::IsReadingPointer(PropertyID) ) \
            { \
                detail::push_back_unique(m_ReadingChildren, pNode); \
                if( CPropertyID::IsWritingPointer(PropertyID) ) \
                { \
                    detail::push_back_unique(m_WritingChildren, pNode); \
                } \
             } \
         }

        // the compiler will optimize the if() statements away if PropertyID is a constant
#	define ADD_CHILD( PropertyID, Property ) \
        INodePrivate *pNode = dynamic_cast<CNodeMap*>(m_pNodeMap)->_GetNodeByID( Property.NodeID() ); \
        if( CPropertyID::IsInvalidatingPointer(PropertyID) )\
        { \
            detail::push_back_unique(m_InvalidatingChildren, pNode);\
            dynamic_cast<CNodeImpl*>(pNode)->SetParent( this );\
            if( CPropertyID::IsReadingPointer(PropertyID) ) \
            { \
                detail::push_back_unique(m_ReadingChildren, pNode);\
                if( CPropertyID::IsWritingPointer(PropertyID) ) \
                { \
                    detail::push_back_unique(m_WritingChildren, pNode); \
                } \
            } \
        }

#else
#	define ADD_ORPHAN_CHILD( PropertyID, Property ) \
        INodePrivate *pNode = dynamic_cast<CNodeMap*>(m_pNodeMap)->_GetNodeByID(Property.NodeID()); \
        add_orphan_child( PropertyID, Property, pNode );

#	define ADD_CHILD( PropertyID, Property ) \
        INodePrivate *pNode = dynamic_cast<CNodeMap*>(m_pNodeMap)->_GetNodeByID(Property.NodeID()); \
        add_child( PropertyID, Property, pNode );

    // This is a helper function performing the same tasks as the macro above 
    // In contrast to the macro however you can set breakpoint here :-)
    void add_child(CPropertyID::EProperty_ID_t PropertyID, CProperty &/*Property*/, INodePrivate *pNode)
    {
        if (CPropertyID::IsInvalidatingPointer(PropertyID))
        {
            detail::push_back_unique(m_InvalidatingChildren, pNode);
            dynamic_cast<CNodeImpl*>(pNode)->SetParent(this);  // this is not present in add_orphan_child
            if (CPropertyID::IsReadingPointer(PropertyID))
            {
                detail::push_back_unique(m_ReadingChildren, pNode);
                if (CPropertyID::IsWritingPointer(PropertyID))
                {
                    detail::push_back_unique(m_WritingChildren, pNode);
                }
            }
        }
    }

    void add_orphan_child(CPropertyID::EProperty_ID_t PropertyID, CProperty &/*Property*/, INodePrivate *pNode)
    {
        if (CPropertyID::IsInvalidatingPointer(PropertyID))
        {
            detail::push_back_unique(m_InvalidatingChildren, pNode);
            if (CPropertyID::IsReadingPointer(PropertyID))
            {
                detail::push_back_unique(m_ReadingChildren, pNode);
                if (CPropertyID::IsWritingPointer(PropertyID))
                {
                    detail::push_back_unique(m_WritingChildren, pNode);
                }
            }
        }
    }
#endif
    private:
        //-------------------------------------------------------------
        // ! \name Interface IUserData
        //@{
            UserData_t GetUserData() const;
            UserData_t SetUserData( UserData_t userdata );
        //@}
    protected:
        //-------------------------------------------------------------
        //! \name Members properties and helpers
        //@{
            GENICAM_NAMESPACE::gcstring GetNodeType() const {
                       std::string nodetype;
                       Value2String(m_NodeTypeEnum, nodetype);
                       
                       return nodetype.c_str();
            }

            //! The name of the node
            GENICAM_NAMESPACE::gcstring m_Name;

            //! The metadata from the extension
            GENICAM_NAMESPACE::gcstring m_Extension;

            //! The namespace of the node
            ENameSpace m_NameSpace;

            //! The device name of the node tree
            GENICAM_NAMESPACE::gcstring m_DeviceName;

            //! The display name string of the node
            GENICAM_NAMESPACE::gcstring m_DisplayName;

            //! The ToolTip for the node
            GENICAM_NAMESPACE::gcstring m_ToolTip;

            //! The Description of the node
            GENICAM_NAMESPACE::gcstring m_Description;

            //! recommended visibility;
            EVisibility m_Visibility;

            //! Reference to a Node, which indicates if the node is implemented
            CBooleanPolyRef m_IsImplemented;

            //! Reference to a Node, which indicates if the node is available
            CBooleanPolyRef m_IsAvailable;

            //! Reference to a Node, which indicates if the node is locked (i.e. not writable)
            CBooleanPolyRef m_IsLocked;

            //! Reference to a Node, which indicates if the node is not cached
            CBooleanPolyRef m_BlockPolling;

            //! Pointer to a Error class
            IEnumeration *m_pError;

            //! Pointer to a Node, which describes the same feature as this one
            INode *m_pAlias;

            //! Pointer to a Node, which describes the same feature as this one so that it can be casted
            INode *m_pCastAlias;

            //! indicates that the node has changed
            mutable ECachingMode m_CachingMode;

            //! List of selected features
            FeatureList_t m_Selected;

            //! List of selecting features
            FeatureList_t m_Selecting;

            //! The EventID
            GENICAM_NAMESPACE::gcstring m_EventID;

            //! indicates if the node is streamable
            EYesNo m_IsStreamable;

            //! Access mode imposed on the natural access mode of the node
            EAccessMode m_ImposedAccessMode;

            //! Visibility imposed to the natural visibility of the node
            EVisibility m_ImposedVisibility;

            //! recommended polling time in [ms]
            int64_t m_PollingTime;

            //! States when propagating terminals
            enum ETerminalPropagationState
            {
                eNotVisited, //!< PropagateTerminals not run for node
                eBeingVisited, //!< PropagateTerminals is in progress for node, used for detecting cycles
                eTerminalPropagationDone //! PropagateTerminals is done for node, can just copy from m_AllTerminalNodes
            };

            //! Current state for propagating terminals
            ETerminalPropagationState m_propagationState;

            //! List of references to nodes which may invalidate this node
            NodeList_t m_Invalidators;

            //! A URL pointing or the documentation of this featrues
            GENICAM_NAMESPACE::gcstring m_DocuURL;

            //! indicates that the feature should not be used any more
            EYesNo m_IsDeprecated;

            //! Helper: A list of all properties belonging to this node
            GENICAM_NAMESPACE::gcstring_vector m_PropertyNames;

            //! indicates that the node is a feature that is reachable from the Root node via categories
            EYesNo m_IsFeature;

        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Implementation of the node dependency handling
        //@{
            //! All nodes for which this node is at least a DependecyChild
            NodePrivateVector_t m_Parents;

            //! all nodes which can be read from 
            //! For details see GenICam wiki : GenApi/SoftwareArchitecture/NodeDependencies
            NodePrivateVector_t m_ReadingChildren;

            //! all nodes which can write a value further down the node stack
            //! For details see GenICam wiki : GenApi/SoftwareArchitecture/NodeDependencies
            NodePrivateVector_t m_WritingChildren;

            //! All directly connected nodes which invalidate this node
            //! For details see GenICam wiki : GenApi/SoftwareArchitecture/NodeDependencies
            NodePrivateVector_t m_InvalidatingChildren;

            //! All directly or indirectly connected nodes which are invalidated by this nodes (i.e. which are dependent on this node)
            //! For details see GenICam wiki : GenApi/SoftwareArchitecture/NodeDependencies
            NodePrivateVector_t m_AllDependingNodes;

            //! All indirectly connected terminal nodes
            //! For details see GenICam wiki : GenApi/SoftwareArchitecture/NodeDependencies
            NodePrivateVector_t m_AllTerminalNodes;

            //! All node use as variable by this node
            NodePrivateVector_t m_VariableChildren;
        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Implementation of the cache
        //@{
            //! stores the cached value of the CachingMode
            mutable ECachingMode m_CachingModeCache;

            //! cache access mode
            mutable EAccessMode m_AccessModeCache;

            inline void CacheAccessModeIfPossible( EAccessMode AccessMode ) const
            {
                m_AccessModeCache = ( Yes == InternalIsAccessModeCacheable() ) ? AccessMode : _UndefinedAccesMode;
            }

            //! true if the value cache is valid
            mutable bool m_ValueCacheValid;

            //! true if the list of valid value is cached
            mutable bool m_ListOfValidValuesCacheValid;

            //! Checks if the value comes from cache or is requested from another node
            virtual bool InternalIsValueCacheValid() const;

            //! indicates if the AccessMode is cacheable
            mutable EYesNo m_AccessModeCacheability;

        //@}

    protected:
        //-------------------------------------------------------------
        //! \name Implementation members and methods
        //@{
            //! Pointer to the node map
            INodeMapPrivate* m_pNodeMap;

            //! time elapsed since the last poll
            int64_t m_ElapsedTime;

            //! shortcut for the lock type
            typedef AutoLock Lock;

            //! Acquire central lock
            CLock& GetLock() const;

            //! The bathometer is a counter used to measure the depth of SetValue-like call chains
            Counter& GetBathometer() const;

            //! Invalidates all nodes which will become affected by a SetValue call into the node tree
            void PreSetValue();

            //! Fires callback on all nodes which became affected by a SetValue call into the node tree
            void PostSetValue( std::list<CNodeCallback*> &CallbacksToFire );

            //! indicates that the cache has been filled and should not be cleared at the end of the operation
            bool m_DontDeleteThisCache;

            //! Used to ensure that PostSetValue() is called in any case
            class PostSetValueFinalizer
            {
            public:
                //! Constructor
                PostSetValueFinalizer(CNodeImpl* pThis,  std::list<CNodeCallback*> &CallbacksToFire ) :
                    m_pThis( pThis ),
                    m_CallbacksToFire( CallbacksToFire )
                {}

                //! Destructor calling PostSetValue()
                ~PostSetValueFinalizer()
                {
                    m_pThis->PostSetValue( m_CallbacksToFire );
                }

                //! pointer to owner object
                CNodeImpl* m_pThis;

                //! list of callbacks to file
                std::list<CNodeCallback*> &m_CallbacksToFire;

            private:
                //! \name Assignment and copying is not supported
                // \{
                PostSetValueFinalizer(const PostSetValueFinalizer&);
                PostSetValueFinalizer& operator=(const PostSetValueFinalizer&);
                // \}
            };

            //! List of callbacks
            std::list<CNodeCallback*> m_Callbacks;

            //! Used to ensure that PostSetValue() is called in any case
            class EntryMethodFinalizer
            {
            public:
                //! Constructor
                EntryMethodFinalizer(const INodePrivate* pThis, EMethod EntryMethod, bool IgnoreCache = false ) 
                {
                    assert(pThis);
                    m_pNodeMapPrivate = dynamic_cast<INodeMapPrivate*>( pThis->GetNodeMap() );
                    m_pNodeMapPrivate->SetEntryPoint( EntryMethod, pThis, IgnoreCache );
                }

                //! Destructor calling 
                ~EntryMethodFinalizer()
                {
                    m_pNodeMapPrivate->ResetEntryPoint();
                }

            private:
                //! Private cache for the INodeMapPrivate pointer
                INodeMapPrivate *m_pNodeMapPrivate;
            };

            //! Creates the full qualified name
            GENICAM_NAMESPACE::gcstring GetQualifiedName(GENICAM_NAMESPACE::gcstring Name, ENameSpace NameSpace) const;

        //@}

        //-------------------------------------------------------------
        //! \name Implementation of the loggers
        //@{
            // for safety reasons please keep these member variables at the
            // end of the class' memory layout

            //! Logger for messages concerning the AccessMode
            LOG4CPP_NS::Category *m_pAccessLog;

            //! Logger for messages concerning the getting and setting values
            LOG4CPP_NS::Category *m_pValueLog;

            //! Logger for messages concerning the range check
            LOG4CPP_NS::Category *m_pRangeLog;

            //! Logger for messages concerning the port access
            LOG4CPP_NS::Category *m_pPortLog;

            //! Logger for messages concerning the caching access
            LOG4CPP_NS::Category *m_pCacheLog;

            //! Logger for things done during pre-processing of the node map, e.g. determining dependencies
            LOG4CPP_NS::Category *m_pPreProcLog;

            //! Logger for messages concerning miscellaneous access which does not fit to the other categories
            LOG4CPP_NS::Category *m_pMiscLog;

        //@}


        //! The node's ID
        NodeID_t m_NodeID;

        CNodeData::ENodeType_t m_NodeTypeEnum;

        EYesNo m_ExposeStatic;
        
        //! Storage of user defined data.
        //! Ownership remains by the user!. Use IUserData interface to access the data.
        UserData_t m_pUserData;

    private:
#if defined( _WIN32 ) && !defined( PHARLAP_WIN32 )
        typedef std::wstring string_t;
        typedef std::wstring::size_type size_type;
        typedef std::wostringstream ostringstream_t;
        typedef wchar_t char_t;
        #define QUALIFY_LITERAL( x ) _L( x )
        #define _L( x ) L ## x
        #define GET_MODULE_FILE_NAME GetModuleFileNameW
        #define GET_CSTR( x ) x.w_str().c_str()
        #define GET_LOCALE_INFO GetLocaleInfoW
#else
        typedef std::string string_t;
        typedef std::string::size_type size_type;
        typedef std::ostringstream ostringstream_t;
        typedef char char_t;
        #define QUALIFY_LITERAL( x ) x
        #define GET_MODULE_FILE_NAME GetModuleFileName
        #define GET_CSTR( x ) x.c_str()
        #define GET_LOCALE_INFO GetLocaleInfo
#endif

        static const size_t MaxPath;
        void GetNodeName( string_t& VariableContent ) const;
        void GetStringStreamContent( const ostringstream_t& Content, string_t& VariableContent ) const;
        void GetVendorName( string_t& VariableContent ) const;
        void GetModelName( string_t& VariableContent ) const;
        void GetStandardNameSpace( string_t& VariableContent ) const;
        void GetNodeValue( const CValuePtr& ptrValue, CNodeImpl::string_t& VariableContent ) const;

    };

    //! Helper function for DeleteDoubleCallbacks
    bool DeleteDoubleCallbacksCompare (GENAPI_NAMESPACE::CNodeCallback* pA, GENAPI_NAMESPACE::CNodeCallback* pB);

    //! deletes double callbacks from list
    void DeleteDoubleCallbacks( std::list<CNodeCallback*> &CallbackList );

}

#endif // ifndef GENAPI_NODE_H
