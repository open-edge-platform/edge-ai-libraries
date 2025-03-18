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
\brief  Definition of interface INodeMapPrivate
\ingroup GenApi_PublicImpl
*/

#ifndef GENAPI_INODEMAPPRIVATE_H
#define GENAPI_INODEMAPPRIVATE_H

#include "Base/GCBase.h"
#include "Exception.h"
#include "../Synch.h"
#include "../Counter.h"
#include "../INodeMap.h"
#include "INodePrivate.h"

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

class CProperty;

namespace GENAPI_NAMESPACE
{
    /**
    \brief NodeMap functions used for initialization
    \ingroup GenApi_PublicImpl
    */
    interface GENAPI_DECL_ABSTRACT INodeMapPrivate : virtual public INodeMap
    {
        /**** Methods to create the node map ****/

        //! Registers a new node in the node map
        virtual void RegisterNode(INodePrivate* pNode, CNodeData::ENodeType_t NodeType, NodeID_t NodeID) = 0;

        //! finalizes construction of the node map
        virtual void FinalConstruct(bool DetermineDependencies) = 0;

        //! Presets the number of nodes in order to resize the containers
        virtual void SetNumNodes(size_t NumNodes) = 0;

        //! Retrieves t Node given the NodeID
        virtual INodePrivate* GetNodeByID(NodeID_t NodeID) = 0;

        //! Sets a property to the node  map itself
        virtual void SetProperty(CProperty &Property) = 0;

        //! Retrieves a property from the node map itself
        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const = 0;

        /**** Methods to handle the call stack at run-time ****/

        //! Returns the object which counts the depth of SetValue() call-chains
        virtual Counter& GetBathometer() = 0;

        //! Sets the node and the method the client call has entered the node map
        virtual void SetEntryPoint( EMethod EntryMethod, const INodePrivate *pEntryNode, bool IgnoreCache ) = 0;

        //! Sets the entry point to undefined
        virtual void ResetEntryPoint() = 0;

        //! Returns the node and the method the client call has entered the node map
        /*! \return true it this information is available, false otherwise
        */
        virtual GENICAM_NAMESPACE::gcstring GetEntryPoint() = 0;

        /**** Miscellaneous****/

        //! Indicates if the GenApi logging is enabled
        virtual bool IsGenApiLoggingEnabled() = 0;

        //! Indicates if the GenApi.Device logging is enabled
        virtual bool IsGenApiDeviceLoggingEnabled() = 0;
    };

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_INODEMAPPROVATE_H
