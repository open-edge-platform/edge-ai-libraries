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
\brief  Definition of interface IBase
\ingroup GenApi_PublicInterface
*/


#ifndef GENAPI_IBASE_H
#define GENAPI_IBASE_H

#include <GenApi/GenApiDll.h>
#include <GenApi/Types.h>
#include <GenApi/Reference.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // IBase interface
    //*************************************************************

    /**
    \brief Base interface common to all nodes
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT IBase
    {
        //! Get the access mode of the node
        virtual EAccessMode GetAccessMode() const = 0;

		//! Virtual destructor enforcing virtual destructor on all derived classes
		virtual ~IBase() = 0;
    };

	// Implementation required for Windows only.
	// Note: the C++ standard >= 11 prohibit pure virtual destructors with a function body
	// in the declaration. Consequently gcc 4.0 and newer reject an inline implementation
	// in the class.
	inline IBase::~IBase()
	{
		// do nothing
	}

    //*************************************************************
    // CBaseRef class
    //*************************************************************

#ifndef DOXYGEN_IGNORE

    /**
    \internal
    \brief Reference to an IBase pointer
    \ingroup GenApi_PublicImpl
    */
    template <class T, class I=T>
    class CBaseRefT : public CReferenceT<T, I>
    {
        typedef CReferenceT<T, I> ref;

    public:
        /*--------------------------------------------------------*/
        // IBase
        /*--------------------------------------------------------*/

        //! Get the access mode of the node
        virtual EAccessMode GetAccessMode() const
        {
            if(ref::m_Ptr)
                return ref::m_Ptr->GetAccessMode();
            else
                return NI;
        }

    };

    //! Reference to an IBase pointer
    //! \ingroup GenApi_PublicImpl
    typedef CBaseRefT<IBase> CBaseRef;

#endif

}
#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_IBASE_H
