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
\brief  Definition of interface INodeMap
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_INODEMAP_H
#define GENAPI_INODEMAP_H

#include <Base/GCBase.h>
#include <GenApi/INode.h>
#include <GenApi/IPort.h>
#include <GenApi/Synch.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{

    //*************************************************************
    // INodeMap interface
    //*************************************************************

    /**
    \brief Interface to access the node map
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT INodeMap
    {
        //! Retrieves all nodes in the node map
        virtual void GetNodes(NodeList_t &Nodes) const =  0;

        //! Retrieves the node from the central map by Name
        virtual INode* GetNode( const GENICAM_NAMESPACE::gcstring& Name) const = 0;

        //! Invalidates all nodes
        virtual void InvalidateNodes() const =  0;

        //! Connects a port to a port node with given name
        virtual bool Connect( IPort* pPort, const GENICAM_NAMESPACE::gcstring& PortName) const = 0;

        //! Connects a port to the standard port "Device"
        virtual bool Connect( IPort* pPort) const = 0;

        //! Get device name
        /*! The device name identifies a device instance, e.g. for debugging purposes.
        The default ist "Device". */
        virtual GENICAM_NAMESPACE::gcstring GetDeviceName() = 0;

        //! Fires nodes which have a polling time
        virtual void Poll( int64_t ElapsedTime ) = 0;

        //! Returns the lock which guards the node map
        virtual CLock& GetLock() const = 0;

        //! Get the number of nodes in the map
        virtual uint64_t GetNumNodes() const  = 0;

        //! Parse all Swissknife equations
        virtual bool ParseSwissKnifes( GENICAM_NAMESPACE::gcstring_vector *pErrorList = NULL ) const = 0;
    };
}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_INODEMAP_H
