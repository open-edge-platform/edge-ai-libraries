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
/// \brief    Portable string vector implementation
/// \ingroup Base_PublicUtilities



#ifndef GENICAM_GCSTRINGLIST_H
#define GENICAM_GCSTRINGLIST_H

#include <Base/GCTypes.h>
#include <Base/GCString.h>

#pragma pack(push, 8)


#if defined (_WIN32) || (defined (__GNUC__) && (defined (__linux__) || defined(__APPLE__) ||  defined(VXWORKS)))


namespace GENICAM_NAMESPACE
{

    /**
    \brief A vector of gcstrings which is a clone of std::vector<std::string>
    \ingroup Base_PublicUtilities
    */
    class GCBASE_API gcstring_vector
    {
        // Nested types
        // ---------------------------------------------------------------------------
    public:
        class GCBASE_API const_iterator
        {
            // Ctor / Dtor
            // -------------------------------------------------------------------------
        public:
            const_iterator(gcstring *pStr = 0);

            // Operators
            // -------------------------------------------------------------------------
        public:
            const gcstring &        operator *        (void)                  const;
            const gcstring *        operator ->       (void)                  const;
            const_iterator &        operator ++       (void);
            const_iterator          operator ++       (int);
            const_iterator &        operator --       (void);
            const_iterator          operator --       (int);
            const_iterator &        operator +=       (intptr_t iInc);
            const_iterator          operator +        (intptr_t iInc)         const;
            const_iterator &        operator -=       (intptr_t iDec);
            intptr_t                operator -        (const const_iterator &iter) const;
            const_iterator          operator -        (intptr_t iDec)         const;
            const gcstring &        operator []       (intptr_t iIndex)       const;
            bool                    operator ==       (const const_iterator &iter) const;
            bool                    operator !=       (const const_iterator &iter) const;
            bool                    operator <        (const const_iterator &iter) const;
            bool                    operator >        (const const_iterator &iter) const;
            bool                    operator <=       (const const_iterator &iter) const;
            bool                    operator >=       (const const_iterator &iter) const;
            GCBASE_API
                friend const_iterator   operator +        (intptr_t iInc, const const_iterator &iter);

            // Member
            // -------------------------------------------------------------------------
        protected:
            gcstring *              _ps;
        };

        class GCBASE_API iterator :
            public const_iterator
        {
            // Ctor / Dtor
            // -------------------------------------------------------------------------
        public:
            iterator(gcstring *pStr = 0);

            // Operators
            // -------------------------------------------------------------------------
        public:
            gcstring &              operator *        (void)                  const;
            gcstring *              operator ->       (void)                  const;
            iterator &              operator ++       (void);
            iterator                operator ++       (int);
            iterator &              operator --       (void);
            iterator                operator --       (int);
            iterator &              operator +=       (intptr_t iInc);
            iterator                operator +        (intptr_t iInc)         const;
            iterator &              operator -=       (intptr_t iDec);
            intptr_t                operator -        (const iterator &iter)  const;
            iterator                operator -        (intptr_t iDec)         const;
            gcstring &              operator []       (intptr_t iIndex)       const;
            GCBASE_API
            friend iterator         operator +        (intptr_t iInc, const iterator &iter);
        };

        // Ctor / Dtor
        // ---------------------------------------------------------------------------
    public:
        gcstring_vector(void);
        explicit                  gcstring_vector(size_t uiSize, const gcstring &str = gcstring());
        gcstring_vector(const gcstring_vector &obj);
        virtual                   ~gcstring_vector(void);

        // Element access
        // ---------------------------------------------------------------------------
    public:
        virtual void              assign(size_t n, const gcstring &val);
        virtual void              clear(void);
        virtual iterator          erase(iterator pos);
        virtual gcstring &        at(size_t uiIndex);
        virtual const gcstring &  at(size_t uiIndex)        const;
        virtual gcstring &        back(void);
        virtual const gcstring &  back(void)                  const;
        virtual iterator          begin(void);
        virtual const_iterator    begin(void)                  const;
        virtual size_t            capacity(void)                  const;
        virtual iterator          end(void);
        virtual const_iterator    end(void)                  const;
        virtual gcstring &        front(void);
        virtual const gcstring &  front(void)                  const;
        virtual size_t            max_size(void)                  const;
        virtual size_t            size(void)                  const;
        virtual iterator          insert(iterator pos, const gcstring &str);
        virtual bool              empty(void)                  const;
        virtual void              pop_back(void);
        virtual void              push_back(const gcstring &str);
        virtual void              resize(size_t uiSize, const gcstring &str = gcstring());
        virtual void              reserve(size_t uiSize);
        virtual bool              contains(const gcstring &str)     const;

        // Do not use the methods below - they only exist for
        // backwards compatibility
        virtual gcstring_vector & assign(const gcstring_vector &obj);
        virtual void              erase(size_t uiIndex);
        virtual void              insert(size_t uiIndex, const gcstring &str);


        // Operators
        // ---------------------------------------------------------------------------
    public:
        gcstring_vector &         operator =        (const gcstring_vector &obj);
        gcstring &                operator []       (size_t uiIndex);
        const gcstring &          operator []       (size_t uiIndex)        const;
        void                      operator delete   (void *pWhere);
        void *                    operator new      (size_t uiSize);

        // Member
        // ---------------------------------------------------------------------------
    private:
        void *                    _pv;
    };

}



#else
#   error No known support for shared libraries
#endif

#pragma pack(pop)

#endif // GENICAM_GCSTRINGLIST_H
