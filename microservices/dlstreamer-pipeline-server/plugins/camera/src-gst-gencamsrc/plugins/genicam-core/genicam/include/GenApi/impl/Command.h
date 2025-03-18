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
\brief    Definition of CCommand
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_COMMAND_H
#define GENAPI_COMMAND_H

#include "../ICommand.h"
#include "Node.h"
#include "BaseT.h"
#include "ValueT.h"
#include "NodeT.h"
#include "CommandT.h"
#include "PolyReference.h"

namespace GENAPI_NAMESPACE
{

    //*************************************************************
    // CCommand class
    //*************************************************************

    /*!
    * \brief ICommand implementation
    *
    * May be used as a toggle, that resets itself
    * Supposed to work together with a IInteger node, e.g. CMaskedInt,
    * for setting the concrete values.
    *
    * \ingroup GenApi_PublicImpl
    */

    class CCommandImpl : public  ICommand, public CNodeImpl
    {
    public:
        //! Constructor
        CCommandImpl();

        //-------------------------------------------------------------
        //! \name IBase implementation
        EAccessMode InternalGetAccessMode() const;

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfICommand;
        }

        //-------------------------------------------------------------
        //! \name INode implementation

        //! Invalidates the node if the polling time has elapsed
        virtual bool Poll( int64_t ElapsedTime );

        //-------------------------------------------------------------
        //! \name IValue implementation
        //\{
        // Get value of the node as string
        virtual GENICAM_NAMESPACE::gcstring InternalToString(bool Verify = false, bool IgnoreCache = false);

        // Set value of the node as string
        virtual void InternalFromString(const GENICAM_NAMESPACE::gcstring& valueString, bool Verify = true);

        // \}

    protected:
        //-------------------------------------------------------------
        //! \name ICommand implementation
        //\{
        // do it!
        virtual void InternalExecute(bool Verify = true);

        // done ?
        virtual bool InternalIsDone(bool Verify, bool &FireCallbacks );
        // \}


    public:
        //! \name INodePrivate implementation
        virtual void SetProperty( CProperty &Property );
        virtual bool GetProperty( CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList ) const;
        
        
        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------

    protected:

        //-------------------------------------------------------------
        // Member variables
        //-------------------------------------------------------------

        //! possible stati of the command node
        typedef enum _EStatus
        {
            statusUninitialized,
            statusIdle,
            statusBusy
         } EStatus;

        //! the internal status of the command node
        EStatus m_Status;

        //! Reference to value or node representing the válue
        CIntegerPolyRef m_Value;

        //! Value for On
        CIntegerPolyRef m_CommandValue;

    };


    class CCommand : public BaseT< ValueT< NodeT< CommandT< CCommandImpl > > > >
    {
    };
}

#endif // GENAPI_COMMAND_H
