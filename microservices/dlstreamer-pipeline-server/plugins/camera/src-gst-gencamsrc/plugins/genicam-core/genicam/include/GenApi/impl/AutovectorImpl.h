//-----------------------------------------------------------------------------
//  (c) 2012 by Teledyne DALSA
//  Section: Digital Imaging
//  Project: GenAPI
//  Author:  Eric Bourbonnais
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
//
/*!
\file
\brief   This file contains the internal implementation of the autovector.
*/

//////////////////////////////////////////////////////////////////////////////

#ifndef GENAPI_GCAUTIVECTOR_H
#define GENAPI_GCAUTIVECTOR_H

#include "GenApi/Autovector.h"
#ifdef _MSC_VER
#   include "GenApi/impl/GlobalPragmas.h"
#endif
#include "GenApi/impl/Value2String.h"
#include <algorithm>


namespace GENAPI_NAMESPACE
{
    template<class T, class Base>
    class _autovector_impl : public Base
    {
    public:
        _autovector_impl() : Base()
        {};

        _autovector_impl(const _autovector_impl &obj) : Base(obj)
        {};

        explicit _autovector_impl(const size_t uiSize)
        {
            // fill with uiSize default values
            Base::_pv->reserve(uiSize);
            for (size_t i = 0; i < uiSize; ++i)
            {
                Base::_pv->push_back(T());
            }
        };

        _autovector_impl(T *values, const size_t count)
        {
            Base::_pv->reserve(count);
            for (size_t index = 0; index < count; index++)
                Base::_pv->push_back(values[index]);
            std::sort(Base::_pv->begin(), Base::_pv->end());

        };

        virtual ~_autovector_impl() {}

        void ToStrings(GENICAM_NAMESPACE::gcstring_vector &srtList) const
        {
            GENICAM_NAMESPACE::gcstring valueStr;
            typename std::vector<T>::const_iterator it;
            for (it = Base::_pv->begin(); it != Base::_pv->end(); it++)
            {
                Value2String(*it, valueStr);
                srtList.push_back(valueStr);
            }
        };

        _autovector_impl & operator= (const Base &obj)
        {
            Base::operator=(obj);
            return *this;
        }
        _autovector_impl & operator= (const _autovector_impl &obj)
        {
            Base::operator=(obj);
            return *this;
        }

        _autovector_impl & operator= (const GENICAM_NAMESPACE::gcstring_vector &obj)
        {
            Base::_pv->clear();
            for (GENICAM_NAMESPACE::gcstring_vector::const_iterator it = obj.begin();
                it != obj.end(); it++)
            {
                T value;
                if (String2Value(*it, &value))
                    Base::_pv->push_back(value);
            }
            std::sort(Base::_pv->begin(), Base::_pv->end());
            return *this;
        }

        const _autovector_impl duplicate(T min, T max)
        {
            _autovector_impl resizeVect;
            typename std::vector<T>::const_iterator it;
            for (it = Base::_pv->begin(); it != Base::_pv->end(); it++)
            {
                if (*it >= min && *it <= max)
                    resizeVect._pv->push_back(*it);
            }
            return resizeVect;
        };

        size_t size() const
        {
            return Base::size();
        }

    };

    typedef _autovector_impl<int64_t, int64_autovector_t> int64_autovector_impl;
    typedef _autovector_impl<double, double_autovector_t> double_autovector_impl;
}

#endif // GENICAM_GCAUTIVECTOR_H
