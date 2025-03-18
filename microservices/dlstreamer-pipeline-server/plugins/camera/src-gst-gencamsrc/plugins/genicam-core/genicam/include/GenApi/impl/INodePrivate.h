//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  MargretAlbrecht
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
\brief    Definition of interface INodePrivate
\ingroup GenApi_PublicImpl
*/


#ifndef GENAPI_INODEPRIVATE_H
#define GENAPI_INODEPRIVATE_H

#include "../GenApiDll.h"
#include "../Types.h"
#include "../INode.h"
#include "../INodeMap.h"
#include "NodeMapData/NodeData.h"

#include <vector>
#include <set>
#include <list>

struct NodeID_t;
class CProperty;

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // INodePrivate interface
    //*************************************************************

    interface INodePrivate;
    interface INodeMapPrivate;

    //! a vector of node references using the INodePrivate interface
    typedef std::vector< INodePrivate* > NodePrivateVector_t;

    /**
    \brief Interface including the methods for node construction common to all nodes
    \ingroup GenApi_PublicImpl
    */
    interface GENAPI_DECL_ABSTRACT INodePrivate : public INode
    {
        /**** Methods to create nodes ****/

        //! Initializes a freshly created node object
        virtual void Initialize(GENAPI_NAMESPACE::INodeMapPrivate* const pNodeMap, CNodeData::ENodeType_t NodeType, NodeID_t &NodeID) = 0;

        //! Reads back the node type
        virtual CNodeData::ENodeType_t GetNodeType() = 0;

        //! Reads back the node id
        virtual NodeID_t GetNodeID() = 0;

        //! Finalizes the creation of a node object
        virtual void FinalConstruct() = 0;

        //! Sets a property to the node
        virtual void SetProperty(CProperty &Property) = 0;

        //! Gets all properties from a node which map a given PropertyID
        // BEWARE: PropertyLsit contains pointers to CProperty objects on the heap. the caller is responsible for deleting them
        //         e.g. by calling CNodeData::FreePropertiesList( PropertyList )
        virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const = 0;

        /**** Methods to handle callbacks ****/

        //! Three different modes of operation for INodePrivate::SetInvalid()
        enum ESetInvalidMode
        {
            simOnlyMe,  //!< Invalidate only the node itself
            simAll  //!< Invalidate the node and all of its dependents
        };

        //! Invalidate the node resp. the node and all of its dependents
        virtual void SetInvalid(ESetInvalidMode simMode) = 0;

        //! Update the registered callbacks
        virtual void CollectCallbacksToFire(std::list<CNodeCallback*> &CallbacksToFire, bool allDependents = false) = 0;

        //! Returns true, if this node is terminal
        virtual bool IsTerminalNode() const = 0;
        
        //! Returns the list of all terminal nodes a write access to this node will eventually write to
        virtual void GetTerminalNodes(NodeList_t &) const = 0;

        //! Invalidates the node if the polling time has elapsed
        /*!
            \return true : fire callback of that node
        */
        virtual bool Poll( int64_t ElapsedTime ) = 0;

    };


}

#endif // ifndef GENAPI_INODEPRIVATE_H
