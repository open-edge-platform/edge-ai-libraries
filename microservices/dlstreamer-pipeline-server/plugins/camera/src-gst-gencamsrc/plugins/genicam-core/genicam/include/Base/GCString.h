/****************************************************************************
(c) 2005 by STEMMER IMAGING

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


****************************************************************************/

/// \file
/// \brief    Portable string implementation
/// \ingroup Base_PublicUtilities


#ifndef GENICAM_GCSTRING_H
#define GENICAM_GCSTRING_H

#include <new>
#include <string>
#include <iostream>
#include <Base/GCTypes.h>

#pragma pack(push, 8)


/** 
\brief Indicates either 'not found' or 'all remaining characters'.
\ingroup GenApi_Implementation
*/
#define GCSTRING_NPOS size_t(-1)

namespace GENICAM_NAMESPACE
{
    /**
    \brief A string class which is a clone of std::string
    \ingroup Base_PublicUtilities
    */
    class GCBASE_API gcstring
    {
#       if defined(_MSC_VER) && !defined(PHARLAP_WIN32)
    public:
            //! Helper class for storing shared-ownership wchar_t *
            class GCBASE_API gcwchar 
            {
            public:
                //! Creates a buffer of \a n wchar_ts
                explicit gcwchar( size_t n );

                // copy constructor
                gcwchar( const gcwchar &rhs );

                // assignment operator
                gcwchar & operator = (const gcwchar &rhs);

                //! Gets the c-string.
                const wchar_t * c_str() const;

                //! Gets the length of the buffer.
                size_t length() const;

                //! destructor 
                ~gcwchar();
            private:
                class impl;
                impl *m_pimpl;
            };

#       endif

        // Ctor / Dtor
        // -------------------------------------------------------------------------
    public:
        gcstring                ();
        gcstring                ( const char *pc );
        gcstring                ( const char *pc, size_t n );
        gcstring                ( size_t count, char ch );
        gcstring                ( const gcstring &str );
#       if defined(_MSC_VER) && !defined(PHARLAP_WIN32)
            explicit gcstring   ( const wchar_t *pBufferUTF16 );
            gcstring            ( const wchar_t *pBufferUTF16, size_t n );
#       endif
        virtual  ~gcstring      ( void );

        // Data access
        // -------------------------------------------------------------------------
    public:
        virtual gcstring &  append                ( const gcstring &str );
        virtual gcstring &  append                ( size_t count, char ch );
        virtual gcstring &  assign                ( const gcstring &str );
        virtual gcstring &  assign                ( size_t count, char ch );
        virtual gcstring &  assign                ( const char *pc );
        virtual gcstring &  assign                ( const char *pc, size_t n );
#       if defined(_MSC_VER) && !defined(PHARLAP_WIN32)
            virtual gcstring &  assign            ( const wchar_t *pStringUTF16 );
            virtual gcstring &  assign            ( const wchar_t *pStringUTF16, int n );
#       endif
        virtual int         compare               ( const gcstring &str )   const;
#       if defined(_MSC_VER) && !defined(PHARLAP_WIN32)
            virtual gcwchar w_str                 ( void )                  const;
#       endif
        virtual const char *c_str                 ( void )                  const;
        virtual bool        empty                 ( void )                  const;
        virtual size_t      find                  ( char ch, size_t offset = 0 ) const;
        virtual size_t      find                  ( const gcstring &str, size_t offset = 0 ) const;
        virtual size_t      find                  ( const gcstring &str, size_t offset, size_t count ) const;
        virtual size_t      find                  ( const char* pc, size_t offset = 0) const;
        virtual size_t      find                  ( const char* pc, size_t offset, size_t count ) const;
        virtual size_t      length                ( void )                  const;
        virtual size_t      size                  ( void )                  const;
        virtual void        resize                ( size_t n );
        virtual size_t      max_size              ( )                       const;
        virtual gcstring    substr                ( size_t offset = 0, size_t count = GCSTRING_NPOS ) const;
        virtual size_t      find_first_of         ( const gcstring &str, size_t offset = 0 ) const;
        virtual size_t      find_first_not_of     ( const gcstring &str, size_t offset = 0 ) const;
        static size_t       _npos                 ( void );
        virtual void        swap                  ( gcstring &Right );


        // Operators
        // -------------------------------------------------------------------------
    public:
        bool                operator !=           ( const gcstring &str )   const;
        bool                operator !=           ( const char *pc )        const;
        gcstring &          operator +=           ( const gcstring &str );
        gcstring            operator +=           ( const gcstring &str )   const;
        gcstring &          operator +=           ( const char *pc );

        gcstring &          operator +=           ( char ch );
        gcstring            operator +=           ( char ch )               const;
        gcstring &          operator =            ( const gcstring &str );
#       if defined(_MSC_VER) && !defined(PHARLAP_WIN32)
            gcstring &          operator =        ( const wchar_t *pStringUTF16 );
#       endif
        bool                operator ==           ( const gcstring &str )   const;
        bool                operator ==           ( const char *pc )        const;
        bool                operator <            ( const gcstring &str )   const;
        bool                operator >            ( const gcstring &str )   const;
        operator const char * ( void )                  const;
        void                operator delete       ( void *pWhere );
        void                operator delete       ( void *pWhere, void *pNewWhere );
        void *              operator new          ( size_t uiSize );
        void *              operator new          ( size_t uiSize, void *pWhere );
        GCBASE_API
        friend gcstring     operator +            ( const gcstring &left, const gcstring &right );
        GCBASE_API
        friend gcstring     operator +            ( const gcstring &left, const char *right );
        GCBASE_API
        friend gcstring     operator +            ( const char *left, const gcstring &right );

        // Member
        // -------------------------------------------------------------------------
    private:
        // redundant pointer to make the possible to see the contents of the string in the debugger
        const char* m_psz;
        // actual std::string object
        uint8_t m_opaqueData[64];
        
        // Constants
        // -------------------------------------------------------------------------
    public:
        // Beware : this static member prevents delay loading
        // use _npos() instead
        static const size_t npos;
    };
}

namespace GENICAM_NAMESPACE
{
    // this is necessary due to the circular dependency between string/exception
    GCBASE_API void ThrowBadAlloc(const char *source, int line);

    //! STL getline
    //! \ingroup Base_PublicUtilities
    inline std::istream &  getline(std::istream& is, GENICAM_NAMESPACE::gcstring& str)
    {
        try
        {
            std::string tmp;
            std::getline(is, tmp);
            str.assign(tmp.c_str(), tmp.size());
        }
        catch(std::bad_alloc &)
        {
            ThrowBadAlloc(__FILE__, __LINE__);
        }
        return is;
    }

    //! STL getline
    //! \ingroup Base_PublicUtilities
    inline std::istream &  getline(std::istream& is, GENICAM_NAMESPACE::gcstring& str, char delim)
    {
        try
        {
            std::string tmp;
            std::getline(is, tmp, delim);
            str.assign(tmp.c_str(), tmp.size());
        }
        catch(std::bad_alloc &)
        {
            ThrowBadAlloc(__FILE__, __LINE__);
        }
        return is;
    }
}



//! STL operator out
//! \ingroup Base_PublicUtilities
inline std::ostream & operator <<(std::ostream &ostr, const GENICAM_NAMESPACE::gcstring &str)
{
    try
    {
        // use formatted output operator of std::string
        ostr << str.c_str();
    }
    catch(std::bad_alloc &)
    {
        GENICAM_NAMESPACE::ThrowBadAlloc(__FILE__, __LINE__);
    }
    return ostr;
}

//! STL operator in
//! \ingroup Base_PublicUtilities
inline std::istream & operator >>(std::istream &istr, GENICAM_NAMESPACE::gcstring &str)
{
    try
    {
        std::string tmp;
        istr >> tmp;
        str.assign(tmp.c_str(), tmp.size());
    }
    catch(std::bad_alloc &)
    {
        GENICAM_NAMESPACE::ThrowBadAlloc(__FILE__, __LINE__);
    }
    return istr;
}

#pragma pack(pop)

#endif // GENICAM_GCSTRING_H
