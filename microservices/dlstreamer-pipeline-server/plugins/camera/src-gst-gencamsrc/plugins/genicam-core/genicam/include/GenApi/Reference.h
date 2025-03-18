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
\brief    Definition of template CReference
\ingroup GenApi_PublicImpl
*/

#ifndef GENAPI_REFERENCE_H
#define GENAPI_REFERENCE_H

#include <GenApi/Types.h>
#include <GenApi/GenApiDll.h>

namespace GENAPI_NAMESPACE
{
    interface IBase;

    //*************************************************************
    // IReference interface
    //*************************************************************

    /**
    \brief Interface to construct a reference
    \ingroup GenApi_PublicImpl
    */
    interface GENAPI_DECL_ABSTRACT IReference
    {
        //! sets the implementation to a reference
        virtual void SetReference( GENAPI_NAMESPACE::IBase *pBase ) = 0;
    };

    //*************************************************************
    // IEnumReference interface
    //*************************************************************

    /**
    \brief Interface to construct an enum reference
    \ingroup GenApi_PublicImpl
    */
    interface GENAPI_DECL_ABSTRACT IEnumReference
    {
        //! sets the Enum value corresponding to a value
        virtual void SetEnumReference( int Index, GENICAM_NAMESPACE::gcstring Name) = 0;

        //! sets the number of enum vallues
        virtual void SetNumEnums( int NumEnums ) = 0;
    };

    //*************************************************************
    // CReference class
    //*************************************************************

    /**
    \brief Reference to an IBase derived pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T, class I=T>
    class CReferenceT : public T, public IReference
    {
    public:
        // Constructor
        CReferenceT() :
            m_Ptr(NULL)
        {}

        /*--------------------------------------------------------*/
        // IReference
        /*--------------------------------------------------------*/

        //! sets the implementation to the reference
        virtual void SetReference( IBase *ptr )
        {
            m_Ptr = dynamic_cast<I*>( ptr );
        }

    protected:
        //! Pointer to the implementation the reference references to
        I *m_Ptr;
    };

}

#endif // ifndef GENAPI_REFERENCE_H
