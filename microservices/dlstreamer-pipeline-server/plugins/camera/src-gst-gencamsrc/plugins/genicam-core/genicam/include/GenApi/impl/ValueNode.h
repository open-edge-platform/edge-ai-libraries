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
\brief    Definition of CValueNode
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_VALUENODE_H
#define GENAPI_VALUENODE_H

#include "../IValue.h"
#include "Node.h"
#include "ValueT.h"
#include "BaseT.h"
#include "NodeT.h"

namespace GENAPI_NAMESPACE
{

    class CValueNodeImpl : public CNodeImpl, virtual public IValue
    {
    protected:

        //-------------------------------------------------------------
        // IValue implementation
        //-------------------------------------------------------------

        //! Get content of the node as string
        virtual GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false);

        //! Set content of the node as string
        virtual void InternalFromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool Verify = true);


        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIValue;
        }


    protected:
        //! Dummy value
        GENICAM_NAMESPACE::gcstring m_Value;
    };

    //*************************************************************
    // CValueNode class
    //*************************************************************

    //! Generic Node with dummy IValue implementation
    /*! This node type is required for testing */

    class CTestValueNode : public BaseT < ValueT< NodeT < CValueNodeImpl > > >
    {
    };

}

#endif // ifndef GENAPI_VALUENODE_H
