; A short tour of TRILISP.
(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
(fact 14)          ; fixnums hold 26 trits: up to 1,270,932,914,164
(define (map f l) (if (null l) nil (cons (f (car l)) (map f (cdr l)))))
(map fact '(1 2 3 4 5 6))
; one trit, three types: the tag of a number, a symbol, a cons
(list (tag 42) (tag 'duwamish) (tag '(a b)))
; beneath the language: 42 is stored as the word 3*42+1
(word 42)
(tprint 42)
; EVAL is tail-recursive: this loop runs in constant stack
(define (count n acc) (if (= n 0) acc (count (- n 1) (+ acc 1))))
(count 5000 0)
; a macro
(defmacro (unless c x) (list 'if c nil x))
(unless (= 1 2) 'fine)
; the self-reproducing expression: its value is itself
(define q '((lambda (x) (list x (list 'quote x))) '(lambda (x) (list x (list 'quote x)))))
(equal (eval q) q)
(explode 'ternary)
