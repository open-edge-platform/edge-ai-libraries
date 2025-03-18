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
\brief    Definition of CMaskedIntReg
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_MASKEDINTREG_H
#define GENAPI_MASKEDINTREG_H

#include "IntReg.h"


namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // CMaskedIntReg class
    //*************************************************************

    //! IInteger implementation for a masked register
    /*! Maps an integer (signed or unsigned) to a masked register
    */
    class CMaskedIntRegImpl : public CIntRegImpl
    {
    public:
        //! Constructor
        CMaskedIntRegImpl();

        //! Implementation of IBase::GetPrincipalInterfaceType()
        virtual EInterfaceType InternalGetPrincipalInterfaceType() const
        {
            return intfIInteger;
        }

        //-------------------------------------------------------------
        // INodePrivate implementation
        //-------------------------------------------------------------


        //! Initializes the object
        virtual void FinalConstruct();

        //-------------------------------------------------------------
        // IRegister implementation
        //-------------------------------------------------------------

        //! Retrieves the Length of the register [Bytes]
        virtual int64_t InternalGetLength();


        //-------------------------------------------------------------
        // IInteger implementation
        //-------------------------------------------------------------

    protected:
        //! Set feature value
        virtual void InternalSetValue(int64_t Value, bool Verify = true);


        //! Get feature value
        virtual int64_t InternalGetValue(bool Verify = false, bool IgnoreCache = false);

    public:


        //-------------------------------------------------------------
        // Initializing
        //-------------------------------------------------------------
        
        
    virtual void SetProperty( CProperty &Property );
    virtual bool GetProperty(CNodeDataMap *pNodeDataMap, CPropertyID::EProperty_ID_t PropertyID, CNodeData::PropertyVector_t &PropertyList) const;
        
    protected:
        //-------------------------------------------------------------
        // Memeber variables
        //-------------------------------------------------------------
        //! least siginificant bit of the integer with respect to the register
        uint32_t  m_LSB;

        //! the property belonging to m_LSB
        uint32_t  m_LSB_property;

        //! most siginificant bit of the integer with respect to the register
        uint32_t  m_MSB;

        //! the property belonging to m_MSB
        uint32_t  m_MSB_property;

        //! Mask with 1 were the integer is located; 0 otherwise
        uint64_t m_Mask;

    };

    class CMaskedIntReg
        : public BaseT< ValueT< NodeT < IntegerT< RegisterT<  CMaskedIntRegImpl> > > > >
    {
    };

}

#endif // GENAPI_MASKEDINTREG_H
