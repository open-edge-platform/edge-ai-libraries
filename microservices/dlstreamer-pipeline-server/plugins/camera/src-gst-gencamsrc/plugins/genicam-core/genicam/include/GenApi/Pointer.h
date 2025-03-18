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
\brief    Definition of template CPointer
\ingroup GenApi_PublicUtilities
*/

#ifndef GENAPI_POINTER_H
#define GENAPI_POINTER_H

#include <assert.h>
#include <GenICamFwd.h>
#include <GenApi/IEnumeration.h>
#include <GenApi/IFloat.h>
#include <GenApi/IInteger.h>

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // CPointer class
    //*************************************************************

    /**
    \brief Encapsulates a GenApi pointer dealing with the dynamic_cast automatically
    \ingroup GenApi_PublicUtilities
    */
    template <class T, class B = IBase>
    class CPointer
    {

    public:
        //! Default constructor.
        CPointer(void) throw()
            : m_pT( NULL )
        {
        }

        //! Constructor from INode pointer type.
        CPointer( B *pB )
            : m_pT( dynamic_cast<T*>(pB) )
        {
        }

        virtual ~CPointer(void)
        {
        }

        //! Assign INode Pointer
        void operator=( B *pB )
        {
            m_pT = dynamic_cast<T*>(pB);
        }

        //! Dereferencing
        operator T*(void) const
        {
            if (NULL == m_pT)
                throw LOGICAL_ERROR_EXCEPTION( "NULL pointer dereferenced" );
            return m_pT;
        }

        //! Dereferencing
        T& operator*(void) const
        {
            if (NULL == m_pT)
                throw LOGICAL_ERROR_EXCEPTION( "NULL pointer dereferenced" );
            return *m_pT;
        }

        //! Dereferencing
        T& operator()(void) const
        {
            if (NULL == m_pT)
                throw LOGICAL_ERROR_EXCEPTION( "NULL pointer dereferenced" );
            return *m_pT;
        }

        //! Dereferencing
        T* operator->(void) const
        {
            if (NULL == m_pT)
                throw LOGICAL_ERROR_EXCEPTION( "NULL pointer dereferenced" );
            return m_pT;
        }

        //! true if the pointer is valid
        bool IsValid() const throw()
        {
            return m_pT != NULL;
        }

        //! true if the pointer is valid
        operator bool(void) const throw()
        {
            return m_pT != NULL;
        }

        //! pointer equal
        bool operator==(T* pT) const 
        {
            return m_pT == pT;
        }

        //! pointer equal
        bool operator==(const CPointer<T,B> &rT) const 
        {
            return m_pT == rT.m_pT;
        }

        //! pointer equal
        bool operator==(int nMustBeNull) const
        {
            if (0 != nMustBeNull)
                throw LOGICAL_ERROR_EXCEPTION( "argument must be NULL" );
            return NULL == m_pT;
        }


    protected:

        //! Underlying raw pointer.
        T* m_pT;
    };

    //*************************************************************
    // Smartpointer for all interface
    //*************************************************************

    //! \addtogroup GenApi_PublicUtilities
    //! \{

    //! SmartPointer for IBase interface pointer
    typedef CPointer<IBase> CBasePtr;

    //! SmartPointer for INode interface pointer
    typedef CPointer<INode> CNodePtr;

    //! SmartPointer for IValue interface pointer
    typedef CPointer<IValue> CValuePtr;

    //! SmartPointer for ICategory interface pointer
    typedef CPointer<ICategory> CCategoryPtr;

    //! SmartPointer for IBoolean interface pointer
    typedef CPointer<IBoolean> CBooleanPtr;

    //! SmartPointer for IInteger interface pointer
    typedef CPointer<IInteger> CIntegerPtr;

    //! SmartPointer for IString interface pointer
    typedef CPointer<IString> CStringPtr;

    //! SmartPointer for IRegister interface pointer
    typedef CPointer<IRegister> CRegisterPtr;

    //! SmartPointer for IEnumeration interface pointer
    typedef CPointer<IEnumeration> CEnumerationPtr;

    //! SmartPointer for IEnumEntry interface pointer
    typedef CPointer<IEnumEntry> CEnumEntryPtr;

    //! SmartPointer for IPort interface pointer
    typedef CPointer<IPort> CPortPtr;

    //! SmartPointer for IPortReplay interface pointer
    typedef CPointer<IPortReplay> CPortReplayPtr;

    //! SmartPointer for IPortRecorder interface pointer
    typedef CPointer<IPortRecorder> CPortRecorderPtr;

    //! SmartPointer for IPortWriteList interface pointer
    typedef CPointer<IPortWriteList, IPortWriteList> CPortWriteListPtr;

    //! SmartPointer for IChunkPort interface pointer
    typedef CPointer<IChunkPort> CChunkPortPtr;

    //! SmartPointer for INodeMap interface pointer
    typedef CPointer<INodeMap, INodeMap> CNodeMapPtr;

    //! SmartPointer for IDeviceInfo interface pointer
    typedef CPointer<IDeviceInfo, INodeMap> CDeviceInfoPtr;

    //! SmartPointer for IUserData interface pointer
    typedef CPointer<IUserData, INodeMap> CNodeMapUserDataPtr;
    //! SmartPointer for IUserData interface pointer
    typedef CPointer<IUserData> CNodeUserDataPtr;

    //! SmartPointer for ISelector interface pointer
    typedef CPointer<ISelector> CSelectorPtr;

    //! SmartPointer for ICommand interface pointer
     typedef CPointer<ICommand> CCommandPtr;

     //! SmartPointer for IFloat interface pointer
    class CFloatPtr : public CPointer<IFloat, IBase>
    {
    public:
        //! Default constructor.
        CFloatPtr() throw()
            : CPointer<IFloat, IBase>(  )
        {
        }

        //! Constructor from IBase pointer type.
        CFloatPtr( IBase *pB )
            : CPointer<IFloat, IBase>( pB )
        {
        }

        //! Assign IBase Pointer
        void operator=( IBase *pB )
        {
            CPointer<IFloat, IBase>::operator =(pB);
        }

        //! gets the interface of an integer alias node.
        IInteger *GetIntAlias()
        {
            return dynamic_cast<IInteger*>(m_pT->GetNode()->GetCastAlias());
        }

        //! gets the interface of an enum alias node.
        IEnumeration *GetEnumAlias()
        {
            return dynamic_cast<IEnumeration*>(m_pT->GetNode()->GetCastAlias());
        }
    };

    //! \}

    //! \addtogroup GenApi_PublicImpl
    //! \{

    //! SmartPointer for IPortConstruct interface pointer
    typedef CPointer<IPortConstruct> CPortConstructPtr;


    //! Returns the name of the main interface as string
    //! DEPRECATED, use IBase::GetPrincipalInterfaceType() instead
    inline GENICAM_NAMESPACE::gcstring GetInterfaceName(IBase *pBase)
    {
#       ifdef _MSC_VER
#           pragma warning (push) // icc -W4 complains: controlling expression is constant
#           pragma warning (disable : 279)
#       endif
        assert(pBase && "don't call this with a NULL pointer");
#       ifdef _MSC_VER
#           pragma warning (pop)
#       endif
        CNodePtr ptrNode(pBase);
        switch(ptrNode->GetPrincipalInterfaceType())
        {
        case intfIValue:
            return GENICAM_NAMESPACE::gcstring("IValue");
        case intfIInteger:
            return GENICAM_NAMESPACE::gcstring("IInteger");
        case intfIBoolean:
            return GENICAM_NAMESPACE::gcstring("IBoolean");
        case intfICommand:
            return GENICAM_NAMESPACE::gcstring("ICommand");
        case intfIFloat:
            return GENICAM_NAMESPACE::gcstring("IFloat");
        case intfIString:
            return GENICAM_NAMESPACE::gcstring("IString");
        case intfIRegister:
            return GENICAM_NAMESPACE::gcstring("IRegister");
        case intfICategory:
            return GENICAM_NAMESPACE::gcstring("ICategory");
        case intfIEnumeration:
            return GENICAM_NAMESPACE::gcstring("IEnumeration");
        case intfIEnumEntry:
            return GENICAM_NAMESPACE::gcstring("IEnumEntry");
        case intfIPort:
            return GENICAM_NAMESPACE::gcstring("IPort");
// Do not use this pragma in public header files (warnings in depend projects): #pragma BullseyeCoverage off
        case intfIBase:
        default:
            return GENICAM_NAMESPACE::gcstring("IBase");
// Do not use this pragma in public header files (warnings in depend projects): #pragma BullseyeCoverage on
        }
    }

    //! Checks if a node is readable
    template <class T, class B>
    inline bool IsReadable( const CPointer<T, B>& ptr)
    {
        return ptr.IsValid() && IsReadable( ptr->GetAccessMode() );
    }

    //! Checks if a node is Writable
    template <class T, class B>
    inline bool IsWritable( const CPointer<T, B>& ptr)
    {
        return ptr.IsValid() && IsWritable( ptr->GetAccessMode() );
    }

    //! Checks if a node is Implemented
    template <class T, class B>
    inline bool IsImplemented( const CPointer<T, B>& ptr)
    {
        return ptr.IsValid() && IsImplemented( ptr->GetAccessMode() );
    }

    //! Checks if a node is Available
    template <class T, class B>
    inline bool IsAvailable( const CPointer<T, B>& ptr)
    {
        return ptr.IsValid() && IsAvailable( ptr->GetAccessMode() );
    }


    //! \}


}

#endif // ifndef GENAPI_POINTER_H
