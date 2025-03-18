//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Hartmut Nebelung
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
\brief    Implementation helpers for CNodeCallback
\ingroup GenApi_PublicImpl

Defines a bunch of templates for creating callback-functors taking a INode pointer
and returning void.

\note does not work with all stl containers, i.e. std::map

*/

#ifndef GENAPI_NODECALLBACK_H
#define GENAPI_NODECALLBACK_H
#include <GenApi/INode.h>

namespace GENAPI_NAMESPACE
{

    //! the type of callback
    typedef enum _ECallbackType
    {
        cbPostInsideLock = 1,   //!> callback is fired on leaving the tree inside the lock-guarded area
        cbPostOutsideLock = 2   //!> callback is fired on leaving the tree outside the lock-guarded area
    } ECallbackType;

    /**
    \brief callback body instance for INode pointers
    \ingroup GenApi_PublicImpl
    */
    class CNodeCallback
    {
    public:
        CNodeCallback( INode *pNode, ECallbackType CallbackType ) :
            m_pNode(pNode),
            m_CallbackType( CallbackType )
        {}

        //! virtual destructor
        virtual ~CNodeCallback()
        {};

        //! fires the callback if the type is right
        virtual void operator()( ECallbackType CallbackType ) const = 0;

        //! destroys the object
        virtual void Destroy() = 0;

        //! returns the node the callback is registered to      
        INode* GetNode()      
        {      
            return m_pNode;      
        }  

    protected:
        //! the node were the callback is installed
        INode *m_pNode;

        //! the type of the callback
        ECallbackType m_CallbackType;
    };

    /***************************************************************************/
    // C Functions as callbacks
    /***************************************************************************/

    /**
    \brief Container for a function pointer
    \ingroup GenApi_PublicImpl
    */
    template <class Function>
    class Function_NodeCallback : public CNodeCallback
    {
    public:
        //! Constructor
        Function_NodeCallback( INode *pNode, const Function& function, ECallbackType CallbackType ) :
            CNodeCallback( pNode, CallbackType ),
            m_pFunction( function )
        {}

        //! execute operation: call the function
        virtual void operator()( ECallbackType CallbackType ) const
        {
            if (m_pFunction && m_CallbackType == CallbackType)
                m_pFunction( m_pNode );
        }

        //! destroys the object
        virtual void Destroy()
        {
            delete this;
        }

    private:
        //! the callback function
        const Function m_pFunction;

        //! no assignment operator
        Function_NodeCallback& operator=(Function_NodeCallback&);
    };

    /*-----------------------------------------------------------------------------*/

    /**
    \brief make a new callback object for C functions
    \ingroup GenApi_PublicImpl
    */
    template <class Function>
    CNodeCallback *make_NodeCallback( INode *pNode, Function function, ECallbackType CallbackType )
    {
        return static_cast<CNodeCallback*>( new Function_NodeCallback<Function>(pNode, function, CallbackType) );
    }

    /*-----------------------------------------------------------------------------*/


    /**
    \brief Register a C-function as a callback
    \ingroup GenApi_PublicUtilities
    */
    template<class Function>
    intptr_t Register( INode* pNode, Function f, ECallbackType CallbackType = cbPostInsideLock )
    {
        CNodeCallback *pCallback(make_NodeCallback(pNode, f, CallbackType));
        return pNode->RegisterCallback(pCallback);
    }


    /***************************************************************************/
    // C++ Member functions as callbacks
    /***************************************************************************/

    /**
    \brief Container for a member function pointer
    \ingroup GenApi_PublicImpl
    */
    template <class Client, class Member>
    class Member_NodeCallback : public CNodeCallback
    {
    public:
        //! Member function type
        typedef void (Client::*PMEMBERFUNC)(INode*);

        //! Constructor
        Member_NodeCallback( INode *pNode, Client& client, Member member, ECallbackType CallbackType ) :
            CNodeCallback( pNode, CallbackType ),
            m_Client(client),
            m_pMemberFunc(member)
        {}

        //! execute operation
        virtual void operator()( ECallbackType CallbackType ) const
        {
            if (m_pMemberFunc && m_CallbackType == CallbackType)
                (m_Client.*m_pMemberFunc)( m_pNode );
        }

        //! destroys the object
        virtual void Destroy()
        {
            delete this;
        }

    private:
        //! The object the method function belongs to
        Client& m_Client;

        //! The method to call
        PMEMBERFUNC m_pMemberFunc;

        //! no assignment operator
        Member_NodeCallback& operator=(Member_NodeCallback&);
    };

    /*-----------------------------------------------------------------------------*/

    /**
    \brief make a new callback object for member functions
    \ingroup GenApi_PublicImpl
    */
    template <class Client, class Member>
    CNodeCallback *make_NodeCallback( INode *pNode, Client& client, Member member, ECallbackType CallbackType )
    {
        return static_cast<CNodeCallback*>( new Member_NodeCallback<Client,Member>(pNode, client, member, CallbackType) );
    }

    /*-----------------------------------------------------------------------------*/

    /**
    \brief Register a C++-member function a callback
    \ingroup GenApi_PublicUtilities
    */
    template<class Client, class Member>
    intptr_t Register( INode* pNode, Client &c, Member m, ECallbackType CallbackType = cbPostInsideLock  )
    {
        CNodeCallback *pCallback(make_NodeCallback(pNode, c, m, CallbackType));
        return pNode->RegisterCallback(pCallback);
    }


    //! Unregistering callback by handle
    // definition in Node.cpp
    GENAPI_DECL void Deregister (GENAPI_NAMESPACE::CallbackHandleType pCallbackInfo );

}

#endif // GENAPI_NODECALLBACK_H
