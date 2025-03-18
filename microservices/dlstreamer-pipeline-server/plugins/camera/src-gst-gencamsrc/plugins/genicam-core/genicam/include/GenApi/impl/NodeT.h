//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Alexander Happe
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
\brief    Definition of the NodeT class template
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_NODET_H
#define GENAPI_NODET_H

#include "../NodeCallback.h"
#include "../INode.h"
#include "../Synch.h"
#include "GenApi/impl/Log.h"
#include "Node.h"
#ifndef _MSC_VER
#include <list>
#endif

namespace GENAPI_NAMESPACE
{

    /**
    \brief Implementation of the INode interface
    */
    template< class Base >
    class NodeT : public Base
    {
    public:
        //! Implementation of INode::GetName()
        virtual GENICAM_NAMESPACE::gcstring GetName(bool FullQualified) const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetName(FullQualified);
        }

        //! Implementation of INode::GetNameSpace()
        virtual GENAPI_NAMESPACE::ENameSpace GetNameSpace() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetNameSpace();
        }

        //! Implementation of INode::GetVisibility()
        virtual EVisibility GetVisibility() const
        {
            AutoLock l(Base::GetLock());

            EVisibility NaturalVisibility = Base::InternalGetVisibility();

            EVisibility Visibility = Combine(NaturalVisibility, Base::m_ImposedVisibility);

            return Visibility;
        }

        //! Implementation of INode::InvalidateNode()
        virtual void InvalidateNode()
        {
            // a list of callbacks to fire held outside(!) the autolock on the stack(!)
            std::list<CNodeCallback*> CallbacksToFire;
            {
                AutoLock l(Base::GetLock());

                Base::InternalInvalidateNode( CallbacksToFire );

                // fire callbacks inside the lock
                std::list<CNodeCallback*>::iterator ptrCallback;
                for( ptrCallback = CallbacksToFire.begin(); ptrCallback != CallbacksToFire.end(); ptrCallback++ )
                {
                    (*ptrCallback)->operator ()(cbPostInsideLock);
                }
            }

            // fire callbacks outside the lock
            std::list<CNodeCallback*>::iterator ptrCallback;
            for( ptrCallback = CallbacksToFire.begin(); ptrCallback != CallbacksToFire.end(); ptrCallback++ )
            {
                (*ptrCallback)->operator ()(cbPostOutsideLock);
            }
        }

        //! Implementation of INode::IsCachable()
        virtual bool IsCachable()const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalIsCachable();
        }

        //! Implementation of INode::GetCachingMode
        virtual ECachingMode GetCachingMode() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetCachingMode();
        }

        //! True if the AccessMode can be cached
        virtual EYesNo IsAccessModeCacheable() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalIsAccessModeCacheable();
        }

        //! Implementation of INode::GetPollingTime()
        virtual int64_t GetPollingTime()const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetPollingTime();
        }

        //! Implementation of INode::GetToolTip()
        virtual GENICAM_NAMESPACE::gcstring GetToolTip() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetToolTip();
        }

        //! Implementation of INode::GetDescription()
        virtual GENICAM_NAMESPACE::gcstring GetDescription() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetDescription();
        }

        //! Implementation of INode::GetDisplayName
        virtual GENICAM_NAMESPACE::gcstring GetDisplayName() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetDisplayName();
        }

        //! Implementation of INode::GetDeviceName
        virtual GENICAM_NAMESPACE::gcstring GetDeviceName() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetDeviceName();
        }

        //! Implementation of INode::GetChildren()
        virtual void GetChildren(NodeList_t &Children, ELinkType LinkType) const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetChildren( Children, LinkType );
        }

        //! Implementation of INode::RegisterCallback()
        virtual CallbackHandleType RegisterCallback( CNodeCallback *pCallback )
        {
            AutoLock l(Base::GetLock());

            return Base::InternalRegisterCallback( pCallback );
        }

        //! Implementation of INode::DeregisterCallback()
        virtual bool DeregisterCallback( CallbackHandleType hCallback )
        {
            AutoLock l(Base::GetLock());

            return Base::InternalDeregisterCallback( hCallback );
        }

        //! Implementation of INode::GetNodeMap()
        virtual INodeMap* GetNodeMap() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetNodeMap();
        }

        //! Implementation of INode::GetNodeMap()
        virtual GENICAM_NAMESPACE::gcstring GetEventID() const
        {
            AutoLock l(Base::GetLock());

            return Base::GetEventID();
        }

        //! Returns a list of the names all properties set during initialization
        virtual void GetPropertyNames(GENICAM_NAMESPACE::gcstring_vector &PropertyNames) const
        {
            AutoLock l(Base::GetLock());

            Base::GetPropertyNames(PropertyNames);
        }

        //! Retrieves a property plus an additional attribute by name
        /*! If a property has multiple values/attribute they come with Tabs as delimiters */
        virtual bool GetProperty(const GENICAM_NAMESPACE::gcstring& PropertyName, GENICAM_NAMESPACE::gcstring& ValueStr, GENICAM_NAMESPACE::gcstring& AttributeStr)
        {
            AutoLock l(Base::GetLock());

            return CNodeImpl::GetProperty(PropertyName, ValueStr, AttributeStr);
        }

        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList)
        {
            AutoLock l(Base::GetLock());

            return Base::GetProperty(pNodeDataMap, PropertyID, PropertyList);
        }


        //! Gets a URL pointing to the documentation of that feature
        virtual GENICAM_NAMESPACE::gcstring GetDocuURL() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetDocuURL();
        }

        //! True if the node should not be used any more
        virtual bool IsDeprecated() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalIsDeprecated();
        }

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType GetPrincipalInterfaceType() const
        {
            AutoLock l(Base::GetLock());

            return Base::InternalGetPrincipalInterfaceType();
        }

    private:
        // suppress assignment operator
        NodeT<Base>& operator=( const NodeT<Base>& );

    };


}

#endif // GENAPI_NODET_H
