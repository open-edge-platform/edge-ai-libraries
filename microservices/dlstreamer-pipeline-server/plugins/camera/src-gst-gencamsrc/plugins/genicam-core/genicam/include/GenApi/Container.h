//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section:  Vision Components
//  Project:  GenApi
//    Author:  Alex Happe
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
/**
\file
\brief    Portable container classes for INode & IValue pointers.
\ingroup GenApi_PublicImpl
*/

#ifndef GENICAM_GENAPI_NODEVECTOR_H
#define GENICAM_GENAPI_NODEVECTOR_H


#include <GenApi/GenApiDll.h>
#include <GenICamFwd.h>

#include <vector>

#ifndef _WIN32
#    include <stdint.h>
#endif

#if defined ( __GNUC__ ) && !defined (VXWORKS) && !defined ( __APPLE__ )
  using namespace __gnu_cxx;
#endif

#if defined ( __GNUC__ ) && defined ( __linux__)
#    include <cstddef>
#endif

#if defined (_WIN32) || (defined (__GNUC__) && (defined (__linux__) || defined (__APPLE__) || defined(VXWORKS)))

// conversion from 'uintptr_t' to 'void *' of greater size
// This is a portability warning
#ifdef _MSC_VER
#   pragma warning( disable : 4312 )
#endif

namespace GENAPI_NAMESPACE
{
    struct INode;
    struct IValue;


    //*************************************************************
    // N O D E _ V E C T O R
    //*************************************************************

    /**
    \brief A vector of INode pointers
    \ingroup GenApi_PublicImpl
    */
    class GENAPI_DECL node_vector
    {
        typedef INode* T;

        // Nested types
        // ---------------------------------------------------------------------------
    public:
        class GENAPI_DECL const_iterator
        {
            // iterator traits
            // ------------------------------------------------------------------------
        public:
            typedef std::random_access_iterator_tag iterator_category;
            typedef T value_type;
            typedef ptrdiff_t difference_type;
            typedef T* pointer;
            typedef T& reference;
            // Ctor / Dtor
            // -------------------------------------------------------------------------
        public:
            const_iterator    ( T *pPtr = 0 );

            // Operators
            // -------------------------------------------------------------------------
        public:
            const T &               operator *        ( void )                  const;
            const_iterator &        operator ++       ( void );
            const_iterator          operator ++       ( int );
            const_iterator &        operator --       ( void );
            const_iterator          operator --       ( int );
            const_iterator &        operator +=       ( intptr_t iInc );
            const_iterator          operator +=       ( intptr_t iInc )         const;
            const_iterator          operator +        ( intptr_t iInc )         const;
            const_iterator &        operator -=       ( intptr_t iDec );
            const_iterator          operator -=       ( intptr_t iDec )         const;
            intptr_t                operator -        ( const const_iterator &iter ) const;
            const_iterator          operator -        ( intptr_t iDec )         const;
            const T &               operator []       ( intptr_t iIndex )       const;
            bool                    operator ==       ( const const_iterator &iter ) const;
            bool                    operator !=       ( const const_iterator &iter ) const;
            bool                    operator <        ( const const_iterator &iter ) const;
            bool                    operator >        ( const const_iterator &iter ) const;
            bool                    operator <=       ( const const_iterator &iter ) const;
            bool                    operator >=       ( const const_iterator &iter ) const;
            GENAPI_DECL
            friend const_iterator   operator +        ( intptr_t iInc, const const_iterator &iter);

            // Member
            // -------------------------------------------------------------------------
        protected:
            T *              _ps;
        };

        class GENAPI_DECL iterator :
            public const_iterator
        {
        public:
            // iterator traits
            // -------------------------------------------------------------------------
            typedef std::random_access_iterator_tag iterator_category;
            typedef T value_type;
            typedef const_iterator::difference_type difference_type;
            typedef const_iterator::pointer pointer;
            typedef const_iterator::reference reference;
            // Ctor / Dtor
            // -------------------------------------------------------------------------
        public:
                                    iterator          ( T *pPtr = 0 );

            // Operators
            // -------------------------------------------------------------------------
        public:
            T &                     operator *        ( void )                  const;
            iterator &              operator ++       ( void );
            iterator                operator ++       ( int );
            iterator &              operator --       ( void );
            iterator                operator --       ( int );
            iterator &              operator +=       ( intptr_t iInc );
            iterator                operator +=       ( intptr_t iInc )         const;
            iterator                operator +        ( intptr_t iInc )         const;
            iterator &              operator -=       ( intptr_t iDec );
            iterator                operator -=       ( intptr_t iDec )         const;
            intptr_t                operator -        ( const iterator &iter )  const;
            iterator                operator -        ( intptr_t iDec )         const;
            T &                     operator []       ( intptr_t iIndex )       const;
            GENAPI_DECL
            friend iterator     operator +        ( intptr_t iInc, const iterator &iter);
        };

        // Ctor / Dtor
        // ---------------------------------------------------------------------------
    public:
                                  node_vector       ( void );
        explicit                  node_vector       ( size_t uiSize);
                                  node_vector       ( const node_vector &obj);
        virtual                   ~node_vector      ( void );

        // Element access
        // ---------------------------------------------------------------------------
    public:
        virtual void              assign            ( size_t n, const T &val );
        virtual void              clear             ( void );
        virtual iterator          erase             ( iterator pos );
        virtual T &               at                ( size_t uiIndex );
        virtual const T &         at                ( size_t uiIndex )        const;
        virtual T &               back              ( void );
        virtual const T &         back              ( void )                  const;
        virtual iterator          begin             ( void );
        virtual const_iterator    begin             ( void )                  const;
        virtual size_t            capacity          ( void )                  const;
        virtual iterator          end               ( void );
        virtual const_iterator    end               ( void )                  const;
        virtual T &               front             ( void );
        virtual const T &         front             ( void )                  const;
        virtual size_t            max_size          ( void )                  const;
        virtual size_t            size              ( void )                  const;
        virtual iterator          insert            ( iterator pos,  const T& val) ;
        virtual bool              empty             ( void )                  const;
        virtual void              pop_back          ( void );
        virtual void              push_back         ( const T &val );
        virtual void              resize            ( size_t uiSize );
        virtual void              reserve           ( size_t uiSize );

        // Do not use - only left in for backwards compatibility!
        virtual void              erase             (size_t uiIndex);
        virtual void              insert            (size_t uiIndex, const T &val);

// Operators
        // ---------------------------------------------------------------------------
    public:
        node_vector &             operator =        ( const node_vector &obj );
        T &                       operator []       ( size_t uiIndex );
        const T &                 operator []       ( size_t uiIndex )        const;
        void                      operator delete   ( void *pWhere );
        void *                    operator new      ( size_t uiSize );

        // Member
        // ---------------------------------------------------------------------------
    private:
       typedef std::vector<T, std::allocator<T> > vector_t;
       vector_t *_pv;
    };



    //*************************************************************
    // V A L U E _ V E C T O R
    //*************************************************************

    /**
    \brief A vector of IValue pointers
    \ingroup GenApi_PublicImpl
    */
    class GENAPI_DECL value_vector
    {
        typedef IValue* T;
        // Nested types
        // ---------------------------------------------------------------------------
    public:
        class GENAPI_DECL const_iterator
        {
            // iterator traits
            // ------------------------------------------------------------------------
        public:
            typedef std::random_access_iterator_tag iterator_category;
            typedef T value_type;
            typedef ptrdiff_t difference_type;
            typedef T* pointer;
            typedef T& reference;

            // Ctor / Dtor
            // -------------------------------------------------------------------------
        public:
            const_iterator    ( T *pPtr = 0 );

            // Operators
            // -------------------------------------------------------------------------
        public:
            const T &               operator *        ( void )                  const;
            const_iterator &        operator ++       ( void );
            const_iterator          operator ++       ( int );
            const_iterator &        operator --       ( void );
            const_iterator          operator --       ( int );
            const_iterator &        operator +=       ( intptr_t iInc );
            const_iterator          operator +=       ( intptr_t iInc )         const;
            const_iterator          operator +        ( intptr_t iInc )         const;
            const_iterator &        operator -=       ( intptr_t iDec );
            const_iterator          operator -=       ( intptr_t iDec )         const;
            intptr_t                operator -        ( const const_iterator &iter ) const;
            const_iterator          operator -        ( intptr_t iDec )         const;
            const T &               operator []       ( intptr_t iIndex )       const;
            bool                    operator ==       ( const const_iterator &iter ) const;
            bool                    operator !=       ( const const_iterator &iter ) const;
            bool                    operator <        ( const const_iterator &iter ) const;
            bool                    operator >        ( const const_iterator &iter ) const;
            bool                    operator <=       ( const const_iterator &iter ) const;
            bool                    operator >=       ( const const_iterator &iter ) const;
            GENAPI_DECL
            friend const_iterator   operator +        ( intptr_t iInc, const const_iterator &iter);

            // Member
            // -------------------------------------------------------------------------
        protected:
            T *              _ps;
        };

        class GENAPI_DECL iterator :
            public const_iterator
        {
        public:
            // iterator traits
            // -------------------------------------------------------------------------
            typedef std::random_access_iterator_tag iterator_category;
            typedef T value_type;
            typedef const_iterator::difference_type difference_type;
            typedef const_iterator::pointer pointer;
            typedef const_iterator::reference reference;
            // Ctor / Dtor
            // -------------------------------------------------------------------------
        public:
            iterator          ( T *pPtr = 0 );

            // Operators
            // -------------------------------------------------------------------------
        public:
            T &                     operator *        ( void )                  const;
            iterator &              operator ++       ( void );
            iterator                operator ++       ( int );
            iterator &              operator --       ( void );
            iterator                operator --       ( int );
            iterator &              operator +=       ( intptr_t iInc );
            iterator                operator +=       ( intptr_t iInc )         const;
            iterator                operator +        ( intptr_t iInc )         const;
            iterator &              operator -=       ( intptr_t iDec );
            iterator                operator -=       ( intptr_t iDec )         const;
            intptr_t                operator -        ( const iterator &iter )  const;
            iterator                operator -        ( intptr_t iDec )         const;
            T &                     operator []       ( intptr_t iIndex )       const;
            GENAPI_DECL
            friend iterator         operator +        ( intptr_t iInc, const iterator &iter);
        };

        // Ctor / Dtor
        // ---------------------------------------------------------------------------
    public:
        value_vector   ( void );
        explicit                  value_vector   ( size_t uiSize);
        value_vector   ( const value_vector &obj);
        virtual                   ~value_vector  ( void );

        // Element access
        // ---------------------------------------------------------------------------
    public:
        virtual void              assign            ( size_t n, const T &obj );
        virtual void              clear             ( void );
        virtual iterator          erase             ( iterator pos );
        virtual T &               at                ( size_t uiIndex );
        virtual const T &         at                ( size_t uiIndex )        const;
        virtual T &               back              ( void );
        virtual const T &         back              ( void )                  const;
        virtual iterator          begin             ( void );
        virtual const_iterator    begin             ( void )                  const;
        virtual size_t            capacity          ( void )                  const;
        virtual iterator          end               ( void );
        virtual const_iterator    end               ( void )                  const;
        virtual T &               front             ( void );
        virtual const T &         front             ( void )                  const;
        virtual size_t            max_size          ( void )                  const;
        virtual size_t            size              ( void )                  const;
        virtual iterator          insert            ( iterator pos,  const T& val) ;
        virtual bool              empty             ( void )                  const;
        virtual void              pop_back          ( void );
        virtual void              push_back         ( const T &val );
        virtual void              resize            ( size_t uiSize, const T &val );
        virtual void              reserve           ( size_t uiSize );


        // Do not use - only left in for backwards compatibility!
        virtual void              erase             (size_t uiIndex);
        virtual void              insert            (size_t uiIndex, const T &val);

// Operators
        // ---------------------------------------------------------------------------
    public:
        value_vector &            operator =        ( const value_vector &obj );
        T &                       operator []       ( size_t uiIndex );
        const T &                 operator []       ( size_t uiIndex )        const;
        void                      operator delete   ( void *pWhere );
        void *                    operator new      ( size_t uiSize );

        // Member
        // ---------------------------------------------------------------------------
    private:
       typedef std::vector<T, std::allocator<T> > vector_t;
       vector_t *_pv;
    };

     //! a list of feature references
    typedef value_vector FeatureList_t;
} // namespace GenApi;


#else
#   error Unknown platform
#endif

#endif // GENICAM_GENAPI_NODEVECTOR_H
