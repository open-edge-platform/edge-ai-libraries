//-----------------------------------------------------------------------------
//  (c) 2015 by Basler
//  Project: GenApi
//  Author:  Fritz Dierks
//  $Header$
//-----------------------------------------------------------------------------
/*!
\file   IUserData.h
\brief  Definition of interface IUserData
*/

#ifndef GENAPI_IUSERDATA_H
#define GENAPI_IUSERDATA_H

#include <GenApi/GenApiDll.h>

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{
    typedef void* UserData_t;
    //*************************************************************
    // IUserData
    //*************************************************************
    /**
    * \ingroup internal_itf
    * \brief Interface to manage user data stored in nodes or nodemaps.
    */

    interface GENAPI_DECL_ABSTRACT IUserData
    {
        //! Returns the stored user defined data.
        virtual UserData_t GetUserData() const = 0;
        //! Stores user defined data without taking ownership. Returns the previously stored value.
        virtual UserData_t SetUserData( UserData_t userdata ) = 0;

    };

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // GENAPI_IUSERDATA_H
